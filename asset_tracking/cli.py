import sys
import argparse
import logging
import argcomplete
import coloredlogs
import datetime
import json

from sqlalchemy import func

from asset_tracking.database.schema import Status, AttributeStatus, Attribute, Asset
from asset_tracking.database.operations import (
    delete_asset,
    get_db_session,
    get_all_assets,
    get_asset_by_name,
    delete_asset,
    get_attribute_by_name,
    update_asset_status,
    remove_attribute,
    update_attribute,
    assign_attribute,
)
from asset_tracking.utils import export_database_to_json_report, load_asset_data_from_json_file
from asset_tracking.core import asset_data_parser, evaluate_status_of_all_assets
from asset_tracking.models import EnrichedAsset


#######################
# Begin CLI functions #
#######################
def build_parser(parser: argparse.ArgumentParser):
    """Build the CLI Argument parser."""

    parser.add_argument("-l", "--list-assets", action="store_true", help="List ALL(!) assets.")
    parser.add_argument("--delete-asset", action="store", default=None, help="Delete an asset by name.")
    parser.add_argument("--debug", action="store_true", default=False, help="Set logging to debug.")
    parser.add_argument(
        "-r",
        "--json",
        dest="raw_results",
        action="store_true",
        help="return results in their raw json format",
    )
    parser.add_argument(
        "-a",
        "--asset-name",
        action="store",
        help="The hostname of an asset to work with. Default returns all asset information.",
    )
    parser.add_argument(
        "-us",
        "--update-asset-status",
        action="store",
        choices=Status.values(),
        help="Update asset status. Use with `-a`.",
    )
    parser.add_argument(
        "-rs",
        "--refresh-asset-statuses",
        action="store_true",
        help="Iterate all assets and evaluate status.",
    )
    parser.add_argument(
        "--export-database",
        action="store_true",
        help="Export database to JSON file that can be converted to CSV.",
    )
    subparsers = parser.add_subparsers(dest="at_command")

    attribute_parser = subparsers.add_parser("attribute", help="Interact with asset attributes.")
    attribute_parser.add_argument(
        "attribute_name",
        action="store",
        help="The name of the attribute to assign or work with.",
    )
    attribute_parser.add_argument(
        "--delete-attribute",
        action="store_true",
        help="delete the resulting attribute from the asset.",
    )
    attribute_parser.add_argument(
        "-d",
        "--attribute-detail",
        action="store",
        default=None,
        help="detail about this asset attribute.",
    )
    attribute_parser.add_argument(
        "-t",
        "--last-observed-time",
        action="store",
        help="Last time this attribute was observed to be true.  Format:'Y-m-d H:M:S' OR 'Y-m-dTH:M:S' UTC",
    )

    import_parser = subparsers.add_parser("import-data", help="Import asset data to update the tracking database with.")
    import_parser.add_argument(
        "json_path",
        action="store",
        help="Path to the data (which should be in JSON format).",
    )
    import_parser.add_argument(
        "-s",
        "--source-name",
        action="store",
        required=True,
        help="The name of the data source IS the attribute name that gets assigned to the asset.",
    )

    unique_attribute_names = []
    with get_db_session() as session:
        results = session.query(Attribute.name).distinct().all()
        unique_attribute_names = [r[0] for r in results]

    filter_parser = subparsers.add_parser("filter", help="Filter the asset tracking database.")
    filter_parser.add_argument(
        "-r",
        "--json",
        dest="raw_results",
        action="store_true",
        help="return results in their raw json format",
    )
    filter_parser.add_argument(
        "--enrich",
        action="store_true",
        help="Enrich asset results with their attributes.",
    )
    filter_parser.add_argument(
        "-s",
        "--asset-status",
        choices=Status.values(),
        action="append",
        default=None,
        help="Get assets with this status",
    )
    filter_parser.add_argument(
        "-ns",
        "--not-asset-status",
        choices=Status.values(),
        action="append",
        default=None,
        help="Get assets that do NOT have this status.",
    )
    filter_parser.add_argument(
        "-as",
        "--attribute-status",
        choices=AttributeStatus.values(),
        action="store",
        default=None,
        help="Filter attributes by this status.",
    )
    # filter_parser.add_argument(
    #    '-nas', '--not-attribute-status', choices=AttributeStatus.values(), action='store', default=None,
    #    help="Filter for attributes that DO NOT have this status."
    # )
    filter_parser.add_argument(
        "-an",
        "--attribute-name",
        action="append",
        choices=unique_attribute_names,
        default=[],
        help="Filter by assets that have an attribute by this name.",
    )
    filter_parser.add_argument(
        "-nan",
        "--not-attribute-name",
        action="append",
        default=[],
        choices=unique_attribute_names,
        help="Filter by assets that DO NOT have an attribute by this name.",
    )


def execute_arguments(args: argparse.Namespace):

    if args.list_assets:
        with get_db_session() as session:
            assets = get_all_assets(session)
        for asset in assets:
            print(asset)
    elif args.delete_asset:
        with get_db_session() as session:
            asset = get_asset_by_name(session, args.delete_asset)
            delete_asset(session, asset)
    elif args.export_database:
        with get_db_session() as session:
            return export_database_to_json_report(session)
    elif args.update_asset_status:
        if not args.asset_name:
            logging.error(f"must also pass asset hostname to work with using `-a` option.")
            return False
        with get_db_session() as session:
            asset = update_asset_status(session, args.asset_name, args.update_asset_status)
            print(asset)
    elif args.at_command == "attribute":
        if not args.asset_name:
            logging.error(f"Asset name must be specified with the `-a` option.")
            return False

        if args.delete_attribute:
            # delete the attribute, if it exists
            with get_db_session() as session:
                attribute = get_attribute_by_name(session, args.asset_name, args.attribute_name)
                if attribute:
                    return remove_attribute(session, attribute)

        # format datetimes as needed
        format_string = "%Y-%m-%d %H:%M:%S"
        if args.last_observed_time and "T" in args.last_observed_time:
            format_string = "%Y-%m-%dT%H:%M:%S"
        last_observed_time = (
            datetime.datetime.strptime(args.last_observed_time, format_string)
            if args.last_observed_time
            else args.last_observed_time
        )
        if not last_observed_time:
            last_observed_time = datetime.datetime.utcnow()

        if not args.last_observed_time and not args.attribute_detail:
            # check is attribute already exists and return it.
            with get_db_session() as session:
                attribute = get_attribute_by_name(session, args.asset_name, args.attribute_name)
                if attribute:
                    if args.raw_results:
                        print(json.dumps(attribute.to_dict(), indent=2))
                    print(f"Found existing: {attribute}")
                    return True
                else:  # if it does not exist, create it.
                    logging.warning(
                        f"No attribute exists by this name and for this asset. To create this attribute, pass attribute detail with the `-d` option."
                    )
                    return attribute
        else:
            # we are either creating or updating
            with get_db_session() as session:
                attribute = get_attribute_by_name(session, args.asset_name, args.attribute_name)
                if attribute:
                    attribute = update_attribute(session, attribute, last_observed_time, args.attribute_detail)
                    print(f"Updated existing attribute: {attribute}")
                    return attribute
                attribute = assign_attribute(
                    session,
                    args.asset_name,
                    args.attribute_name,
                    last_observed_time,
                    args.attribute_detail,
                )
                print(f"Created: {attribute}")
                return attribute
    elif args.asset_name:
        with get_db_session() as session:
            asset = get_asset_by_name(session, args.asset_name)
            if asset:
                enriched_asset = EnrichedAsset(asset)
                if args.raw_results:
                    print(json.dumps(enriched_asset.to_dict(), indent=2))
                    return
                print(f"found:\n  {enriched_asset}")
                return
    elif args.at_command == "import-data":
        data = load_asset_data_from_json_file(args.json_path)
        if not data:
            logging.error(f"no data loaded!")
            return False
        asset_data_parser(data, attribute_name=args.source_name)
    elif args.at_command == "filter":
        with get_db_session() as session:
            # outerjoin or join?
            # query = session.query(Asset).outerjoin(Attribute).filter(Asset.id == Attribute.asset_id)
            # query = session.query(Attribute.asset_id)
            # query = session.query(Asset, Attribute.name).outerjoin(Attribute).group_by(Attribute.asset_id)#
            # query = session.query(Asset, func.group_concat(Attribute.name.distinct()).label('Attributes')).outerjoin(Attribute).filter(Asset.id == Attribute.asset_id)
            query = (
                session.query(
                    Asset,
                    func.group_concat(Attribute.name.distinct()).label("AttributeNames"),
                )
                .join(Attribute)
                .group_by(Attribute.asset_id)
            )

            if args.asset_status:
                # query = query.filter(Asset.status == args.asset_status)
                query = query.filter(Asset.status.in_(args.asset_status))
            if args.not_asset_status:
                query = query.filter(~Asset.status.in_(args.not_asset_status))
                # if args.asset_status == args.not_asset_status:
                #    logging.error(f"your filter doesn't make any sense: {args.asset_status} and NOT {args.not_asset_status}?!")
                #    return False
                # query = query.filter(Asset.status != args.not_asset_status)

            if args.attribute_status:
                query = query.filter(Attribute.status == args.attribute_status)

            # if args.attribute_name:
            #    query = query.filter(Attribute.name.in_(args.attribute_name))
            # for an in args.attribute_name:
            #    query = query.filter(Attribute.name == an)

            # if args.not_attribute_name:
            #    query = query.filter(~Attribute.name.in_(args.not_attribute_name))

            logging.debug(f"Constructed this query: {query}")

            results = query.all()
            if not results:
                return None

            assets = []
            # HACK filter because I was in a hurry and *sqlalchemy*
            if args.attribute_name and args.not_attribute_name:
                assets = [
                    a[0]
                    for a in results
                    if all(an in a[1].split(",") for an in args.attribute_name)
                    and not any(an in a[1].split(",") for an in args.not_attribute_name)
                ]
            elif args.attribute_name:
                assets = [a[0] for a in results if all(an in a[1].split(",") for an in args.attribute_name)]
            elif args.not_attribute_name:
                assets = [a[0] for a in results if not any(an in a[1].split(",") for an in args.not_attribute_name)]
            else:
                assets = [a[0] for a in results]

        if args.raw_results:
            if args.enrich:
                assets = [EnrichedAsset(r).to_dict() for r in assets]
            else:
                assets = [r.to_dict() for r in assets]
            print(json.dumps(assets))
            return
        for asset in assets:
            if args.enrich:
                print(EnrichedAsset(asset))
            else:
                print(asset)
    elif args.refresh_asset_statuses:
        with get_db_session() as session:
            evaluate_status_of_all_assets(session)

    return


def main(args=None):
    """The main CLI entry point."""

    # configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - [%(levelname)s] %(message)s",
    )
    coloredlogs.install(level="INFO", logger=logging.getLogger())

    if not args:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(description="Asset Hostname Tracking CLI")
    build_parser(parser)
    argcomplete.autocomplete(parser)
    args = parser.parse_args(args)

    if args.debug:
        coloredlogs.install(level="DEBUG", logger=logging.getLogger())

    return execute_arguments(args)
