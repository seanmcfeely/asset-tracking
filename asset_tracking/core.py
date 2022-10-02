import logging
import datetime
import json
from telnetlib import SE
import dateutil.parser

from typing import List, Union, Dict

from sqlalchemy.orm import Session

from asset_tracking.config import get_settings
from asset_tracking.database.schema import Asset, Attribute, AttributeStatus, Status
from asset_tracking.database.operations import (
    create_asset,
    get_all_assets,
    get_asset_attributes,
    update_asset_observation_time,
    update_asset_status,
    update_attribute,
    get_db_session,
    get_asset_by_name,
    update_asset_observation_time,
    create_asset,
    get_attribute_by_name,
    assign_attribute,
)


SETTINGS = get_settings()


def time_since_observation(item: Union[Attribute, Asset]) -> datetime.timedelta:
    """Return the time since last observation."""
    if not item.last_observed:
        return datetime.timedelta(days=0)

    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    return now - item.last_observed_time


def evaluate_age_of_all_attributes_and_update_status(
    session: Session,
    attributes: List[Attribute],
    max_attribute_absence=SETTINGS.max_attribute_absence,
):
    """Update attribute status to `missing` if attribute hasn't been seen in `max_attribute_absence` days."""
    for attribute in attributes:
        elapsed_time = time_since_observation(attribute)
        logging.debug(f"elapsed time since attribute({attribute.id}) checked in: {elapsed_time}")
        if elapsed_time > datetime.timedelta(days=max_attribute_absence):
            # update status to missing
            logging.info(f"updating {attribute.id}:{attribute.name} as missing for asset={attribute.asset_id}")
            update_attribute(session, attribute, status=AttributeStatus.missing)
        elif attribute.status == AttributeStatus.missing:
            logging.info(f"updating {attribute.id}:{attribute.name} as good for asset={attribute.asset_id}")
            update_attribute(session, attribute, status=AttributeStatus.good)
    return attributes


def evaluate_asset_attributes_and_update_status(session: Session, asset: Asset, evaluate_attribute_status=True):
    """Execute the logic to change asset status.

    Take into consideration:
        1. Required security tools
        2. Observation age
    """

    # check age of device and update to unknown, if not unknown or rogue
    elapsed_time = time_since_observation(asset)
    logging.debug(f"elapsed time since asset({asset.id}) checked in: {elapsed_time}")
    if elapsed_time > datetime.timedelta(days=SETTINGS.max_asset_absence):
        if asset.status not in [Status.unknown, Status.rogue]:
            logging.info(
                f"{asset.hostname} hasn't been observed in '{elapsed_time}' - updating status from {asset.status.value} to unknown."
            )
            update_asset_status(session, asset, Status.unknown)
            return
        logging.info(
            f"{asset.hostname} hasn't been observed in '{elapsed_time}' and remains in {asset.status.value} state."
        )
        return

    attributes = get_asset_attributes(session, asset)
    if evaluate_attribute_status:
        logging.debug(f"evaluating attribute statuses for {asset.hostname}")
        attributes = evaluate_age_of_all_attributes_and_update_status(
            session, attributes, max_attribute_absence=SETTINGS.max_attribute_absence
        )

    logging.debug(f"evaluating for all {SETTINGS.require_all_attributes} and any of {SETTINGS.require_one_attribute}")
    if not SETTINGS.require_all_attributes and not SETTINGS.require_one_attribute:
        logging.warning(f"Zero security tools required; every asset will be considered compliant.")
        update_asset_status(session, asset, Status.compliant.value)
        return

    required_tool_count = len(SETTINGS.require_all_attributes)
    if SETTINGS.require_one_attribute:
        required_tool_count += 1
    asset_tool_count = required_tool_count

    attribute_names = [a.name.lower() for a in attributes if a.status == AttributeStatus.good]
    has_all_of_these_security_tools = all(tool.lower() in attribute_names for tool in SETTINGS.require_all_attributes)
    has_any_of_these_security_tools = any(tool.lower() in attribute_names for tool in SETTINGS.require_one_attribute)

    compliant = True
    if SETTINGS.require_all_attributes and not has_all_of_these_security_tools:
        asset_tool_count -= len(SETTINGS.require_all_attributes)
        compliant = False
    if compliant and SETTINGS.require_one_attribute and not has_any_of_these_security_tools:
        asset_tool_count -= 1
        compliant = False

    if compliant:
        logging.debug(
            f"{asset.hostname} is compliant with {asset_tool_count}/{required_tool_count} required security tools."
        )
        update_asset_status(session, asset, Status.compliant.value)
    else:
        logging.debug(
            f"{asset.hostname} is non-compliant with {asset_tool_count}/{required_tool_count} required security tools."
        )
        if asset.status == Status.rogue:
            logging.warning(f"{asset.hostname} is classified as a rogue device.")
            # leave the status as rogue, which would mean the asset was discovered as rogue and STILL doesn't have any security tools.
            # This should mean that the device was observed in logs (windows authentication, for instance) indicating a level of risk
            # via unapproved connectivity within the environment.
            return
        if asset.status != Status.non_compliant:
            logging.info(f"marking {asset.hostname} as non-compliant.")
            update_asset_status(session, asset, Status.non_compliant.value)

    return


def evaluate_status_of_all_assets(session: Session, evaluate_attribute_status=True):
    """Iterate all assets and update status.

    Update to `missing` if attribute hasn't been seen in `SETTINGS.max_attribute_absence` days.
    Else, continue to evaluate attributes and reflect asset status accordingly.
    """

    for asset in get_all_assets(session):
        logging.info(f"evaluating attributes to set {asset.hostname} status as complant or non-compliant.")
        evaluate_asset_attributes_and_update_status(session, asset, evaluate_attribute_status=evaluate_attribute_status)


DEFAULT_DATA_FIELD_MAP = {
    "hostname": ["hostname", "name", "displayName"],
    "last_observed": [
        "last_observed",
        "event_time",
        "_time",
        "approximateLastSignInDateTime",
        "last_contact_time",
    ],
    "detail": ["attribute_detail"],  # If None, uses the event itself.
}


def asset_data_parser(
    data: List[Dict],
    field_map=DEFAULT_DATA_FIELD_MAP,
    attribute_name=None,
    evaluate_attribute_status=False,
):
    """Parse data and update the tracking database.

    All data should enter the database through this function.

    The attribute_name is the source identifier of this asset data.

    The following fields are expected to exist in the data:
        - name or hostname
        - _time or event_time
        - _raw or detail or the data itself is used
    """
    logging.info(f"parsing {len(data)} data item for asset tracking...")
    for event in data:

        if attribute_name is None:
            attribute_name = event.get("attribute_name")
            if not attribute_name:
                logging.error(f"no attribute_name supplied... meaningless...")
                continue

        for hostname_key in field_map.get("hostname", []):
            hostname = event.get(hostname_key)
            if hostname:
                hostname = hostname[hostname.rfind("\\") + 1 :] if "\\" in hostname else hostname
                break
        if not hostname:
            logging.error(f"failed to get a hostname from event ... ")
            continue

        for detail_key in field_map.get("detail", []):
            detail = event.get(detail_key)
            if detail:
                break
        if not detail:
            detail = event  # default
        try:
            detail = json.dumps(detail)
        except:
            detail = str(detail)

        for time_key in field_map.get("last_observed", []):
            observed_time = event.get(time_key)
            if observed_time:
                break
        if not observed_time:
            logging.error(f"failed to get observation time ... ")
            continue

        if not isinstance(observed_time, datetime.datetime):
            try:
                observed_time = dateutil.parser.isoparse(observed_time)
            except Exception as e:
                logging.debug(f"failed to parse time: {e}")
                pass
            try:
                observed_time = dateutil.parser.parse(observed_time)
            except Exception as e:
                logging.debug(f"failed to parse time: {e}")
                pass
            if not isinstance(observed_time, datetime.datetime):
                logging.error(f"failed to parse observation time: {observed_time}")
                continue

        with get_db_session() as session:
            # get or create the asset
            asset = get_asset_by_name(session, hostname)
            if asset:
                logging.info(f"Found existing {asset}")
            else:
                asset = create_asset(session, hostname, last_observed=observed_time)
                if not asset:
                    logging.error(f"failed to create {asset}")
                    continue
                logging.info(f"Created new {asset}")

            if not asset.last_observed_time or (observed_time and observed_time > asset.last_observed_time):
                logging.info(f"updating observation time.")
                update_asset_observation_time(session, asset, observed_time)

            # does this attribute already exist?
            attribute = get_attribute_by_name(session, asset, attribute_name)
            if attribute:
                # is our current data newer?
                if observed_time > attribute.last_observed_time:
                    # update the attribute and continue
                    attribute = update_attribute(session, attribute, observed_time, detail)
                    if not attribute:
                        logging.error(f"failed to update attribute for unknown reasons.")
                        continue
                    logging.info(f"updated {attribute}")
                else:
                    logging.info(f"not updating attribute because its data appears older than our current attribute")
                    continue
            else:
                # create/assign the attribute
                attribute = assign_attribute(session, asset, attribute_name, observed_time, detail)
                if not attribute:
                    logging.error(f"failed to create attribute for unknown reasons.")
                    continue
                logging.info(f"assigned {attribute}")

            # If here, something changed; update the assets status as needed.
            evaluate_asset_attributes_and_update_status(
                session, asset, evaluate_attribute_status=evaluate_attribute_status
            )
