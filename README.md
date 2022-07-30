# asset-tracking

Track assets by hostname across enterprise toolsets for analyst context and rouge device detection.


# Data sources

The input data can be any logs that relate to an asset by hostname, for example:

  - {your vendor} EDR logs
  - Azure AD device logs
  - {your vendor} Anti-Virus logs
  - Windows logs

You can also configure requirements as to what an asset has to have
as a recently logged security tool (such as your EDR and AV clients).


# Database

A Postgres database is recommended.

```
CREATE DATABASE asset_tracking;
CREATE USER asset_tracker WITH ENCRYPTED PASSWORD 'yourpass';
GRANT ALL PRIVILEGES ON DATABASE asset_tracking TO asset_tracker;
```

If a Postgres database is not configured and found, a local sqlite database will be used.

# Configuration

You can configure the `asset-tracker` via environment variables and/or configuration files.

Environment variables available for configuration:

| Environment Variable                               | Default             | Description                                                              |
| -------------------------------------------------- | ------------------- | ------------------------------------------------------------------------ |
| ASSET_TRACKING_DATA_DIR                            | Current working dir | Only used if you use SqLite for the database.                            |
| ASSET_TRACKING_SERVER_HOSTNAME_REGEX_STANDARD      |                     | Regex to match your enterprise server names.                             |
| ASSET_TRACKING_WORKSTATION_HOSTNAME_REGEX_STANDARD |                     | " " workstation names.                                                   |
| ASSET_TRACKING_DB_USER                             | postgres            | Postgres username                                                        |
| ASSET_TRACKING_DB_PASS                             |                     | Postgres user password                                                   |
| ASSET_TRACKING_DB_HOST                             |                     | Postgres server hostname                                                 |
| ASSET_TRACKING_DB_PORT                             | 5432                | Postgres port                                                            |
| ASSET_TRACKING_REQUIRE_ALL_ATTRIBUTES              |                     | Comma separated list of required security attributes (tools/log sources) |
| ASSET_TRACKING_REQUIRE_ONE_ATTRIBUTE               |                     | Comma separated list of which an asset has to have one to be compliant.  |
| ASSET_TRACKING_CONFIG_PATH                         |                     | Path to a .ini config file that can be used to override all settings.    |

Default paths searched for configuration files:

```
/etc/ace/asset_tracking.ini
~/.config/asset_tracking.ini
```

Finally, any configuration file pointed to by the ASSET_TRACKING_CONFIG_PATH environment variable overrides any previous configuration items.

The configuration loaded from disk will be checked for settings if an environment variable was not explicitly set for any settings.


# CLI Tool


```
 asset-tracker -h
usage: asset-tracker [-h] [-l] [--delete-asset DELETE_ASSET] [-r] [--from-stdin] [-a ASSET_NAME] [-us {compliant,non_compliant,unknown,rogue}] [-rs]
                     [--export-database]
                     {attribute,import-data,filter} ...

Asset Hostname Tracking CLI

positional arguments:
  {attribute,import-data,filter}
    attribute           Interact with asset attributes.
    import-data         Import asset data to update the tracking database with.
    filter              Filter the asset tracking database.

optional arguments:
  -h, --help            show this help message and exit
  -l, --list-assets     List ALL(!) assets.
  --delete-asset DELETE_ASSET
                        Delete an asset by name.
  -r, --json            return results in their raw json format
  -a ASSET_NAME, --asset-name ASSET_NAME
                        The hostname of an asset to work with. Default returns all asset information.
  -us {compliant,non_compliant,unknown,rogue}, --update-asset-status {compliant,non_compliant,unknown,rogue}
                        Update asset status. Use with `-a`.
  -rs, --refresh-asset-statuses
                        Iterate all assets and evaluate status.
```