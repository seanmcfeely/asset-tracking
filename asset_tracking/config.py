import os
from functools import lru_cache
import logging
from typing import List, Union

from configparser import ConfigParser
from pydantic import BaseSettings, Field


HOME_PATH = os.path.dirname(os.path.abspath(__file__))


default_config_path = os.path.join(HOME_PATH, "etc", "defaults.ini")
user_config_path = os.path.join(os.path.expanduser("~"), ".config", "asset_tracking.ini")
CONFIG_SEARCH_PATHS = [
    default_config_path,
    "/etc/ace/asset_tracking.ini",
    user_config_path,
]

if os.environ.get("ASSET_TRACKING_CONFIG_PATH"):
    CONFIG_SEARCH_PATHS.append(os.environ["ASSET_TRACKING_CONFIG_PATH"])

CONFIG = ConfigParser()
CONFIG.read(CONFIG_SEARCH_PATHS)


@lru_cache()
def get_settings():
    return Settings()


class Settings(BaseSettings):
    default_data_dir: str = Field("", env="ASSET_TRACKING_DATA_DIR")
    default_server_hostname_regex_standard: str = Field("", env="ASSET_TRACKING_SERVER_HOSTNAME_REGEX_STANDARD")
    default_workstation_hostname_regex_standard: str = Field(
        "", env="ASSET_TRACKING_WORKSTATION_HOSTNAME_REGEX_STANDARD"
    )
    default_db_user: str = Field("", env="ASSET_TRACKING_DB_USER")
    default_db_pass: str = Field("", env="ASSET_TRACKING_DB_PASS")
    default_db_host: str = Field("", env="ASSET_TRACKING_DB_HOST")
    default_db_port: str = Field("", env="ASSET_TRACKING_DB_PORT")
    db_name: str = Field("asset_tracking")
    max_attribute_absence: int = Field(4)
    max_asset_absence: int = Field(6)

    @property
    def data_dir(self) -> str:
        if self.default_data_dir != "":
            return self.default_data_dir
        elif CONFIG.has_option("asset_tracking", "data_dir"):
            return CONFIG["asset_tracking"]["data_dir"]
        return os.getcwd()

    @property
    def server_hostname_regex_standard(self) -> str:
        if self.default_server_hostname_regex_standard != "":
            return self.default_server_hostname_regex_standard
        elif CONFIG.has_option("asset_tracking", "server_hostname_regex_standard"):
            return CONFIG["asset_tracking"]["server_hostname_regex_standard"]
        return self.default_server_hostname_regex_standard

    @property
    def workstation_hostname_regex_standard(self) -> str:
        if self.default_workstation_hostname_regex_standard != "":
            return self.default_workstation_hostname_regex_standard
        elif CONFIG.has_option("asset_tracking", "workstation_hostname_regex_standard"):
            return CONFIG["asset_tracking"]["workstation_hostname_regex_standard"]
        return self.default_workstation_hostname_regex_standard

    @property
    def db_user(self) -> str:
        if self.default_db_user != "":
            return self.default_db_user
        elif CONFIG.has_option("asset_tracking", "db_user"):
            return CONFIG["asset_tracking"]["db_user"]
        return "postgres"

    @property
    def db_pass(self) -> str:
        if self.default_db_pass != "":
            return self.default_db_pass
        elif CONFIG.has_option("asset_tracking", "db_pass"):
            return CONFIG["asset_tracking"]["db_pass"]
        return ""

    @property
    def db_host(self) -> str:
        if self.default_db_host != "":
            return self.default_db_host
        elif CONFIG.has_option("asset_tracking", "db_host"):
            return CONFIG["asset_tracking"]["db_host"]
        return ""

    @property
    def db_port(self) -> str:
        if self.default_db_port != "":
            return self.default_db_port
        elif CONFIG.has_option("asset_tracking", "db_port"):
            return CONFIG["asset_tracking"]["db_port"]
        return "5432"

    @property
    def postgres_dsn(self) -> Union[str, None]:
        if not all([self.db_pass, self.db_host]):
            return None

        return "postgresql+pg8000://{}:{}@{}:{}/{}".format(
            self.db_user, self.db_pass, self.db_host, self.db_port, self.db_name
        )

    @property
    def require_all_attributes(self) -> List:
        required_attributes: List[str] = []
        if "ASSET_TRACKING_REQUIRE_ALL_ATTRIBUTES" in os.environ:
            required_attributes_str = os.environ.get("ASSET_TRACKING_REQUIRE_ALL_ATTRIBUTES")
            if isinstance(required_attributes_str, str) and "," in required_attributes_str:
                required_attributes = required_attributes_str.split(",")
            else:
                logging.warning(
                    f"ASSET_TRACKING_REQUIRE_ALL_ATTRIBUTES is not a comma separated list: {required_attributes_str}"
                )
                return []
        return required_attributes

    @property
    def require_one_attribute(self) -> List:
        required_attributes: List[str] = []
        if "ASSET_TRACKING_REQUIRE_ONE_ATTRIBUTE" in os.environ:
            required_attributes_str = os.environ.get("ASSET_TRACKING_REQUIRE_ONE_ATTRIBUTE")
            if isinstance(required_attributes_str, str) and "," in required_attributes_str:
                required_attributes = required_attributes_str.split(",")
            else:
                logging.warning(
                    f"ASSET_TRACKING_REQUIRE_ONE_ATTRIBUTE is not a comma separated list: {required_attributes_str}"
                )
                return []
        return required_attributes

    class Config:
        env_prefix = "ASSET_TRACKING_"
