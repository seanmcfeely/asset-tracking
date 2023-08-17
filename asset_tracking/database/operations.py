import logging
import datetime
import contextlib

from typing import Union
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session as ORMSession
from sqlalchemy_utils import database_exists, create_database

from asset_tracking.config import get_settings
from asset_tracking.database.schema import Base, Status, AttributeStatus, Asset, Attribute


SETTINGS = get_settings()

# TODO: move these to config settings
DATABASE_PATH = f"{SETTINGS.data_dir}/asset_tracking_database.sqlite"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


if SETTINGS.postgres_dsn:
    engine = create_engine(url=SETTINGS.postgres_dsn)
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

Session: ORMSession = sessionmaker(autocommit=False, autoflush=True, bind=engine)


@contextlib.contextmanager
def get_db_session():
    """Get a database session."""
    if SETTINGS.multiprocessing_connection_pools:
        engine.dispose(close=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()


def create_asset(db: Session, hostname: str, status: str = Status.unknown.value, last_observed=None):
    if not Status.has_value(status):
        logging.error(f"{status} is not a valid asset status.")
        return False
    asset = Asset(hostname=hostname.upper(), status=status, last_observed=last_observed)
    db.add(asset)
    try:
        db.commit()
    except IntegrityError as e:
        logging.error(f"failed to create asset by hostname={hostname}: {e}")
        return False
    db.refresh(asset)
    return asset


def update_asset_status(db: Session, asset: Union[Asset, int, str], status):
    loaded_asset: Asset = _get_asset_by_unknown(db, asset)
    if not loaded_asset:
        return loaded_asset
    loaded_asset.status = status
    db.commit()
    db.refresh(loaded_asset)
    return loaded_asset


def update_asset_observation_time(db: Session, asset: Union[Asset, int, str], observed_time: datetime.datetime):
    loaded_asset: Asset = _get_asset_by_unknown(db, asset)
    if not loaded_asset:
        return loaded_asset
    loaded_asset.last_observed = observed_time
    db.commit()
    db.refresh(loaded_asset)
    return asset


def delete_asset(db: Session, asset: Union[Asset, int, str]):
    asset = _get_asset_by_unknown(db, asset)
    if not asset:
        return asset
    # also delete all asset attributes
    for attribute in get_asset_attributes(db, asset):
        db.delete(attribute)
    db.delete(asset)
    db.commit()
    return True


def get_asset_by_id(db: Session, asset_id):
    return db.query(Asset).filter(Asset.id == asset_id).first()


def get_asset_by_name(db: Session, asset_name):
    # case-insensitive lookup by forcing uppercase
    return db.query(Asset).filter(func.upper(Asset.hostname) == asset_name.upper()).first()


def get_all_assets(db: Session):
    return db.query(Asset).all()


def _get_asset_by_unknown(db: Session, asset: Union[Asset, int, str]):
    if isinstance(asset, Asset):
        return asset
    if isinstance(asset, int):
        return get_asset_by_id(db, asset)
    if isinstance(asset, str):
        return get_asset_by_name(db, asset)
    return None


def _get_asset_id(db: Session, asset: Union[Asset, int, str]):
    if isinstance(asset, Asset):
        return asset.id
    if isinstance(asset, int):
        return asset
    if isinstance(asset, str):
        return get_asset_by_name(db, asset).id
    return None


def assign_attribute(
    db: Session,
    asset: Union[Asset, int, str],
    attribute_name: str,
    last_observed: datetime.datetime,
    detail: str,
    status: AttributeStatus = AttributeStatus.good,
):
    """Assign a new attribute to an asset by asset ID."""
    asset_id = _get_asset_id(db, asset)
    if not asset_id:
        logging.warning(f"no asset found for {asset}")
        return False
    attribute = Attribute(
        asset_id=asset_id,
        name=attribute_name,
        last_observed=last_observed,
        detail=detail,
        status=status,
    )
    db.add(attribute)
    db.commit()
    db.refresh(attribute)
    return attribute


def get_attribute_by_name(db: Session, asset: Union[Asset, int, str], attribute_name: str):
    asset_id = _get_asset_id(db, asset)
    query = db.query(Attribute).filter(Attribute.asset_id == asset_id).filter(Attribute.name == attribute_name)
    if not query.count():
        logging.debug(f"no attribute by name={attribute_name} for asset id={asset_id} found.")
        return None
    attribute = query.first()
    return attribute


def get_attribute_by_id(db: Session, attribute_id: int):
    return db.query(Attribute).filter(Attribute.id == attribute_id).first()


def get_asset_attributes(db: Session, asset: Union[Asset, int, str]):
    asset_id = _get_asset_id(db, asset)
    if not asset_id:
        return None
    return db.query(Attribute).filter(Attribute.asset_id == asset_id).all()


def get_unique_attribute_names(db: Session):
    return [n[0] for n in db.query(Attribute.name).distinct().all()]


def update_attribute(
    db: Session,
    attribute: Attribute,
    last_observed: datetime.datetime = None,
    detail: str = None,
    status: AttributeStatus = None,
):
    """Update observed time and/or detail for an existing attribute by asset ID and attribute name."""
    if last_observed is not None:
        attribute.last_observed = last_observed
    if detail is not None:
        attribute.detail = detail
    if isinstance(status, AttributeStatus):
        attribute.status = status
    db.commit()
    db.refresh(attribute)
    return attribute


def remove_attribute(db: Session, attribute: Attribute):
    """Remove an attribute from this asset."""
    db.delete(attribute)
    db.commit()
    return True


def create_tables():
    """Create the database tables."""
    Base.metadata.create_all(bind=engine)


if not database_exists(engine.url):
    create_database(engine.url)

try:
    create_tables()
except Exception as e:
    logging.error(f"problem creating database tables: {e}")
