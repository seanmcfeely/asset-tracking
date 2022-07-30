from asset_tracking.database.operations import (
    get_db_session,
    get_asset_attributes,
    get_asset_by_id,
)
from asset_tracking.database.schema import Asset, Attribute
from asset_tracking.core import evaluate_asset_attributes_and_update_status


class EnrichedAsset:
    """A helper class for loading assets with their attributes."""

    # TODO have this class update status based on time and attributes
    def __init__(self, asset: Asset):
        self.asset = asset
        self.attributes = self.get_attributes()

    def get_attributes(self):
        with get_db_session() as session:
            return get_asset_attributes(session, self.asset)

    def evaluate_asset(self):
        with get_db_session() as session:
            # make the asset persistent in this session to updates are reflected
            self.asset = get_asset_by_id(session, self.asset.id)
            evaluate_asset_attributes_and_update_status(session, self.asset)

    def __str__(self):
        self.evaluate_asset()
        txt = f"{self.asset}"
        for attribute in self.attributes:
            txt += "\n\t" + "\u21B3" + f" {attribute}"
        return txt

    def to_dict(self):
        self.evaluate_asset()
        data = self.asset.to_dict()
        data["attributes"] = [attribute.to_dict() for attribute in self.attributes]
        return data
