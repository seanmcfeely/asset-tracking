import contextlib
import enum
import logging
import datetime
import dateutil
import json

from sqlalchemy import (
    Column,
    Enum,
    ForeignKey,
    DateTime,
    Integer,
    String,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


Base: declarative_base = declarative_base()


class Status(enum.Enum):
    """
    Asset Status.

    Can be one of:
        - compliant: Company owned asset, managed by IT, and has ALL security toolsets required for the device type.
        - non_compliant: Company owned asset, not managed by IT and/or missing some or all of the security toolsets required for the device type.
        - unknown: Unable to identify ownership of device with additional research required.
        - rogue: A device NOT KNOWN to be owned by the company with unapproved connectivity within the environment. Detection point and needs to be addressed.

    NOTE: AzureAD device status is used as the authority on company ownership and management of devices.
          However, a device with ALL required security observed authenticating via windows logs will be considered compliant.
    """

    compliant = "compliant"
    non_compliant = "non_compliant"
    unknown = "unknown"
    rogue = "rogue"

    @classmethod
    def has_value(cls, value):
        return value in set(item.value for item in cls)

    @classmethod
    def values(cls):
        return [item.value for item in cls]


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    hostname = Column(String, unique=True, index=True)
    status = Column(Enum(Status), default="unknown")
    insert_date = Column(DateTime, default=datetime.datetime.utcnow)
    last_observed = Column(DateTime, default=None)
    attributes = relationship("Attribute", back_populates="asset")

    def __str__(self):
        insert_date = self.insert_date.strftime("%Y-%m-%d %H:%M:%S")
        last_observed = self.last_observed.strftime("%Y-%m-%d %H:%M:%S") if self.last_observed else self.last_observed
        return f"Asset: ID={self.id}, Hostname={self.hostname}, Status={self.status.name}, Insert Date={insert_date}, Last Observed={last_observed}"

    def to_dict(self):
        return {
            "id": self.id,
            "hostname": self.hostname,
            "status": self.status.value,
            "insert_date": self.insert_date.isoformat(),
            "last_observed": self.last_observed_time.isoformat() if self.last_observed else self.last_observed,
        }

    @property
    def last_observed_time(self):
        # database does not know `last_observed` is UTC
        if not self.last_observed:
            return None
        return self.last_observed.replace(tzinfo=dateutil.tz.UTC)


class AttributeStatus(enum.Enum):
    good = "good"
    missing = "missing"

    @classmethod
    def has_value(cls, value):
        return value in set(item.value for item in cls)

    @classmethod
    def values(cls):
        return [item.value for item in cls]


class Attribute(Base):
    """Something we know about the asset, like a tool we have on it.

    NOTE: These are meant to be temporary and should be expired after a time period.
    TODO: Expire after a time period. Add a TTL.
    """

    __tablename__ = "asset_attributes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), index=True)
    name = Column(String, index=True)
    last_observed = Column(DateTime, default=datetime.datetime.utcnow)
    detail = Column(String)  # store log that proves it?
    status = Column(Enum(AttributeStatus), default="good")
    asset = relationship("Asset", back_populates="attributes")

    def __str__(self):
        last_observed = self.last_observed.strftime("%Y-%m-%d %H:%M:%S")
        return f"Attribute ID={self.id}: Asset ID={self.asset_id} has {self.name} with {self.status}, Last Observed={last_observed}, Detail Length={len(self.detail)}"

    def to_dict(self):
        detail = self.detail
        try:
            detail = json.loads(self.detail)
        except json.decoder.JSONDecodeError:
            pass

        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "attribute_name": self.name,
            "status": self.status.value,
            "last_observed": self.last_observed.isoformat(),
            "detail": detail,
        }

    @property
    def last_observed_time(self):
        return self.last_observed.replace(tzinfo=dateutil.tz.UTC)
