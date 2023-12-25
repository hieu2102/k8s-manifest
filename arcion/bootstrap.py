import os
import sys
import subprocess
import shutil
import shortuuid
import requests
import base64
import boto3
import random
import ntplib
import dotenv

from ec2_metadata import ec2_metadata
from jinja2 import Environment, FileSystemLoader

# with open("/etc/resolv.conf", "r") as f:
#     if "8.8.8.8" not in f.read():
#         with open("/etc/resolv.conf", "r") as original:
#             data = original.read()
#         with open("/etc/resolv.conf", "w") as modified:
#             modified.write("nameserver 8.8.8.8\n" + data)


ENV_FILE_PATH = os.environ.get("ENV_FILE_PATH")
if ENV_FILE_PATH:
    dotenv.load_dotenv(dotenv_path=ENV_FILE_PATH, override=True)

ARCION_LICENSE_FILE = "/config/replicant.lic"
ARCION_LICENSE = os.environ.get("ARCION_LICENSE")

CLOUD_SERVICE_PROVIDER = os.environ.get("CLOUD_SERVICE_PROVIDER")
NTP_SERVER = os.getenv("NTP_SERVER", "time.google.com")

if not os.path.exists(ARCION_LICENSE_FILE) and not ARCION_LICENSE:
    print(
        "License file /config/replicant.lic does not exist, either supply it or pass as Bas64 using ARCION_LICENSE environment variable, exiting"
    )
    sys.exit(1)

DB = os.environ.get("DB")
if not DB:
    print("Environment variable DB not defined, defaulting to POSTGRESQL")
    DB = "POSTGRESQL"

if not (DB == "POSTGRESQL" or DB == "MYSQL"):
    print("Environment variable DB only supports POSTGRESQL or MYSQL, exiting")
    sys.exit(1)

DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_DATABASE = os.environ.get("DB_DATABASE")
DB_USERNAME = os.environ.get("DB_USERNAME")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_SECRET = os.environ.get("DB_SECRET")

if DB_SECRET and not CLOUD_SERVICE_PROVIDER:
    print(
        "For database connection Secrets Manager usage a Cloud Service Provider needs to be defined"
    )
    sys.exit(1)

if not DB_HOST:
    print("Environment variable DB_HOST not defined, exiting")
    sys.exit(1)
if not DB_PORT:
    if DB == "POSTGRESQL":
        print("Environment variable DB_PORT not defined, defaulting to 5432")
        DB_PORT = 5432
    if DB == "MYSQL":
        print("Environment variable DB_PORT not defined, defaulting to 3306")
        DB_PORT = 3306

if not DB_SECRET:
    if not DB_USERNAME:
        print("Environment variable DB_USERNAME not defined, exiting")
        sys.exit(1)
    if not DB_PASSWORD:
        print("Environment variable DB_PASSWORD not defined, exiting")
        sys.exit(1)
else:
    print("DB_SECRET defined, using Secret Manager")

try:
    client = ntplib.NTPClient()
    response = client.request(NTP_SERVER, timeout=2)
except Exception as error:
    print(
        "Unable to query NTP server "
        + NTP_SERVER
        + ". To specify a different (local) NTP server set the hostname via the NTP_SERVER environment variable"
    )
    sys.exit(1)

if DB == "POSTGRESQL":
    DB_PROTOCOL = "jdbc:postgresql"
    DB_DRIVER = "org.postgresql.Driver"
    if not DB_DATABASE:
        print("Environment variable DB_DATABASE not defined, exiting")
        sys.exit(1)
    if DB_SECRET:
        DB_USERNAME = DB_SECRET
        DB_PASSWORD = ""
        DB_PROTOCOL = "jdbc-secretsmanager:postgresql"
        DB_DRIVER = "com.amazonaws.secretsmanager.sql.AWSSecretsManagerPostgreSQLDriver"
if DB == "MYSQL":
    DB_PROTOCOL = "jdbc:mysql"
    DB_DRIVER = "org.mariadb.jdbc.Driver"
    DB_DATABASE = ""
    if DB_SECRET:
        DB_USERNAME = DB_SECRET
        DB_PASSWORD = ""
        DB_PROTOCOL = "jdbc-secretsmanager:mariadb"
        DB_DRIVER = "com.amazonaws.secretsmanager.sql.AWSSecretsManagerMariaDBDriver"

MODE = os.environ.get("MODE")
CLUSTER_NAME = os.environ.get("CLUSTER_NAME")
CLUSTER_S3_BUCKET = os.environ.get("CLUSTER_S3_BUCKET")
CLUSTER_S3_REGION = os.environ.get("CLUSTER_S3_REGION")
CLUSTER_NODE_NAME = os.environ.get("CLUSTER_NODE_NAME")
CLUSTER_NODE_MODE = os.environ.get("CLUSTER_NODE_MODE")

if CLUSTER_S3_BUCKET and not CLUSTER_S3_REGION:
    print(
        "Environment variable CLUSTER_S3_REGION not defined, it is mandatory if CLUSTER_S3_BUCKET is defined"
    )
    sys.exit(1)

if CLUSTER_S3_BUCKET:
    try:
        s3 = boto3.client("s3", region_name=CLUSTER_S3_REGION)
        objects = s3.list_objects_v2(Bucket=CLUSTER_S3_BUCKET, MaxKeys=1)
    except Exception as error:
        print("Error while testing S3 connectivity")
        print(error)
        sys.exit(1)

if not MODE:
    print("Environment variable MODE not defined, defaulting to AIO")
    MODE = "AIO"
if not CLUSTER_NAME:
    # print('Environment variable CLUSTER_NAME not defined, defaulting to main_cluster\n')
    CLUSTER_NAME = "main_cluster"


# Instance Metadata Service v2 has a default IP hop limit of 1. This can mean that you can see requests.exceptions.ReadTimeout
# errors from within Docker containers. To solve this, reconfigure your EC2 instance’s metadata options to allow three hops
# with aws ec2 modify-instance-metadata-options
def fetch_aws_instance_id():
    try:
        return ec2_metadata.instance_id
    except:
        print("Error while fetching AWS EC2 metadata, skipping...")
        return None
    else:
        return None


INSTANCE_ID = None
if CLOUD_SERVICE_PROVIDER == "AWS":
    INSTANCE_ID = fetch_aws_instance_id()

# Construct node name
# 1. Chek CLUSTER_NODE_NAME environment variable, if exists use that
# 2. Check if we are running on an EC2 instance, if yes use the instanceId as the first part of the node name followed by _
# 3. Check the HOSTNAME env variable which should contain the conatinerId, use that as the seconda part of the name - if empty generate a short UUID

# TODO: For ECS lets look into https://docs.aws.amazon.com/AmazonECS/latest/developerguide/container-metadata.html to get the containerId

if not CLUSTER_NODE_NAME:
    CLUSTER_NODE_NAME = "" if not INSTANCE_ID else INSTANCE_ID + "_"
    HOSTNAME = os.environ.get("HOSTNAME")
    if not HOSTNAME:
        CLUSTER_NODE_NAME += shortuuid.uuid()
    else:
        CLUSTER_NODE_NAME += HOSTNAME
    print(
        "Environment variable CLUSTER_NODE_NAME not defined, defaulting to "
        + CLUSTER_NODE_NAME
    )

if not CLUSTER_NODE_MODE:
    CLUSTER_NODE_MODE = "GENERAL"
    print(
        "Environment variable CLUSTER_NODE_MODE not defined, defaulting to "
        + CLUSTER_NODE_MODE
    )

if (
    CLUSTER_NODE_MODE != "GENERAL"
    and CLUSTER_NODE_MODE != "SNAPSHOT"
    and CLUSTER_NODE_MODE != "REALTIME"
):
    print(
        "Environment variable CLUSTER_NODE_MODE allowed values are GENERAL, SNAPSHOT and REALTIME"
    )
    sys.exit(1)

NEW_RELIC_LICENSE_KEY = os.environ.get("NEW_RELIC_LICENSE_KEY")
if not NEW_RELIC_LICENSE_KEY:
    NEW_RELIC_COMPUTE = ""
    NEW_RELIC_CM = ""
    NEW_RELIC_MANAGEMENT = ""
    NEW_RELIC_REPLICANT = ""
    NEW_RELIC_LOG_PATTERN = ""
    NEW_RELIC_REGION = "US"
else:
    NEW_RELIC_COMPUTE = (
        "-javaagent:/opt/newrelic/newrelic.jar -Dnewrelic.environment=compute"
    )
    NEW_RELIC_CM = (
        "-javaagent:/opt/newrelic/newrelic.jar -Dnewrelic.environment=cluster_manager"
    )
    NEW_RELIC_MANAGEMENT = (
        "-javaagent:/opt/newrelic/newrelic.jar -Dnewrelic.environment=management"
    )
    NEW_RELIC_REPLICANT = (
        "-javaagent:/opt/newrelic/newrelic.jar -Dnewrelic.environment=replicant"
    )
    NEW_RELIC_REGION = os.getenv("NEW_RELIC_REGION", "US")
    NEW_RELIC_LOG_PATTERN = "replicant.core.log-pattern=%d{HH:mm:ss.SSS} [%t] [replicant] [#{organizationId}] [#{replicationId}] %-5level %logger{35} - %msg %n"
    print(f"New Relic region set to ${NEW_RELIC_REGION}")
    os.makedirs("/opt/newrelic/cm/", exist_ok=True)
    os.makedirs("/opt/newrelic/management/", exist_ok=True)
    os.makedirs("/opt/newrelic/compute/", exist_ok=True)

IPV6_ENABLED = os.getenv("IPV6_ENABLED", "True").lower() in ("true", "1", "t")
PROMETHEUS_ENABLE = os.getenv("PROMETHEUS_ENABLE", "False").lower() in (
    "true",
    "1",
    "t",
)

DATA = {
    "DB_PROTOCOL": DB_PROTOCOL,
    "DB_DRIVER": DB_DRIVER,
    "DB_HOST": DB_HOST,
    "DB_PORT": DB_PORT,
    "DB_DATABASE": DB_DATABASE,
    "DB_USERNAME": DB_USERNAME,
    "DB_PASSWORD": DB_PASSWORD,
    "DB_SECRET": DB_SECRET,
    "MANAGEMENT_PORT": 8081,
    "COMPUTE_PORT": 8082,
    "PROMETHEUS_PORT": 8083,
    "CLUSTER_NAME": CLUSTER_NAME,
    "CLUSTER_S3_BUCKET": CLUSTER_S3_BUCKET,
    "CLUSTER_S3_REGION": CLUSTER_S3_REGION,
    "CLUSTER_NODE_NAME": CLUSTER_NODE_NAME,
    "CLUSTER_NODE_MODE": CLUSTER_NODE_MODE,
    "NEW_RELIC_LICENSE_KEY": NEW_RELIC_LICENSE_KEY,
    "NEW_RELIC_REGION": NEW_RELIC_REGION,
    "NEW_RELIC_ENABLE": "true" if NEW_RELIC_LICENSE_KEY else "false",
    "CLOUD_LOGGER_FILENAME": "/arcion/internal-config/core/newrelic.yaml"
    if NEW_RELIC_LICENSE_KEY
    else "",
    "NEW_RELIC_COMPUTE": NEW_RELIC_COMPUTE,
    "NEW_RELIC_CM": NEW_RELIC_CM,
    "NEW_RELIC_MANAGEMENT": NEW_RELIC_MANAGEMENT,
    "NEW_RELIC_REPLICANT": NEW_RELIC_REPLICANT,
    "NEW_RELIC_LOG_PATTERN": NEW_RELIC_LOG_PATTERN,
    "CLOUD_SERVICE_PROVIDER": CLOUD_SERVICE_PROVIDER,
    "IPV6_ENABLED": IPV6_ENABLED,
    "NTP_SERVER": NTP_SERVER,
    "PROMETHEUS_ENABLE": PROMETHEUS_ENABLE,
    "AUTHENTICATION_TYPE": os.getenv("AUTHENTICATION_TYPE", "IN_MEMORY"),
    "IN_MEMORY_USERNAME": os.getenv("USERNAME", "admin"),
    "IN_MEMORY_PASSWORD": os.getenv("PASSWORD", "arcion"),
    "LDAP_URLS": os.environ.get("LDAP_URLS"),
    "LDAP_BASE_DN": os.environ.get("LDAP_BASE_DN"),
    "LDAP_DN_PATTERNS": os.environ.get("LDAP_USER_DN_PATTERNS"),
    "LDAP_SEARCH_FILTER": os.environ.get("LDAP_USER_SEARCH_FILTER"),
    "LDAP_SEARCH_BASE": os.environ.get("LDAP_USER_SEARCH_BASE"),
    "ISSUER_URI": os.environ.get("ISSUER_URI"),
    "AUTHORIZATION_URI": os.environ.get("AUTHORIZATION_URI"),
    "TOKEN_URI": os.environ.get("TOKEN_URI"),
    "CLIENT_ID": os.environ.get("CLIENT_ID"),
    "CLIENT_SECRET": os.environ.get("CLIENT_SECRET"),
    "USER_INFO_AUTH": os.getenv("USER_INFO_AUTH", "HEADER"),
    "USER_INFO_URI": os.environ.get("USER_INFO_URI"),
    "USERNAME_ATTRIBUTE": os.getenv("USERNAME_ATTRIBUTE", "sub"),
    "OAUTH2_SCOPES_SPACE": os.getenv(
        "OAUTH2_SCOPES", "offline_access openid profile email"
    ),
    "OAUTH2_SCOPES": ",".join(
        os.getenv("OAUTH2_SCOPES", "offline_access openid profile email")
        .strip()
        .split()
    ),
    "OAUTH2_REDIRECT_URI": os.getenv(
        "OAUTH2_REDIRECT_URI", "{baseUrl}/{action}/oauth2/code/{registrationId}"
    ),
}

os.makedirs("/data/cm/trace", exist_ok=True)
os.makedirs("/data/compute", exist_ok=True)

environment = Environment(loader=FileSystemLoader("/arcion/templates/"))


def create(template_location, destination):
    template = environment.get_template(template_location)
    rendered_template = template.render(DATA)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with open(destination, mode="w", encoding="utf-8") as configFile:
        configFile.write(rendered_template)


def copytree(src, dst):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if not os.path.isdir(s):
            shutil.copy(s, d)


# Core config files

if DB == "POSTGRESQL":
    create(
        "core/metadata.json.postgresql.txt",
        "/arcion/internal-config/core/metadata.json",
    )
    create(
        "core/metadata.yaml.postgresql.txt",
        "/arcion/internal-config/core/metadata.yaml",
    )
if DB == "MYSQL":
    create("core/metadata.json.mysql.txt", "/arcion/internal-config/core/metadata.json")
    create("core/metadata.yaml.mysql.txt", "/arcion/internal-config/core/metadata.yaml")
create("core/general.yaml.txt", "/arcion/internal-config/core/general.yaml")
create("core/statistics.yaml.txt", "/arcion/internal-config/core/statistics.yaml")

# Cluster manager config files

if DB == "POSTGRESQL":
    create(
        "cm/metadata.json.postgresql.txt", "/arcion/internal-config/cm/metadata.json"
    )
    create(
        "cm/metadata.yaml.postgresql.txt", "/arcion/internal-config/cm/metadata.yaml"
    )
if DB == "MYSQL":
    create("cm/metadata.json.mysql.txt", "/arcion/internal-config/cm/metadata.json")
    create("cm/metadata.yaml.mysql.txt", "/arcion/internal-config/cm/metadata.yaml")
create("cm/cluster.json.txt", "/arcion/internal-config/cm/cluster.json")
create("cm/cluster.yaml.txt", "/arcion/internal-config/cm/cluster.yaml")
create(
    "cm/replicate-cluster-manager.txt",
    "/arcion/release/arcion-on-premises/cm/bin/replicate-cluster-manager",
)

# Compute config files

create(
    "compute/application.properties.txt",
    "/arcion/internal-config/compute/application.properties",
)

# Web UI config files

create("ui/services.json.txt", "/arcion/internal-config/ui/services.json")

# NGINX config file

if MODE == "COMPUTE":
    create("nginx/nginx-compute.conf.txt", "/etc/nginx/nginx.conf")
else:
    create("nginx/nginx.conf.txt", "/etc/nginx/nginx.conf")

# Supervisor config file

if MODE == "COMPUTE":
    create("supervisor/supervisord-compute.conf.txt", "/etc/supervisord.conf")
elif MODE == "UI":
    create("supervisor/supervisord-ui.conf.txt", "/etc/supervisord.conf")
else:
    create("supervisor/supervisord.conf.txt", "/etc/supervisord.conf")

if NEW_RELIC_LICENSE_KEY:
    create("newrelic/newrelic.yml.txt", "/opt/newrelic/newrelic.yml")
    create("core/newrelic.yaml.txt", "/arcion/internal-config/core/newrelic.yaml")

if ARCION_LICENSE:
    try:
        decodedLicense = base64.b64decode(ARCION_LICENSE)
        with open(ARCION_LICENSE_FILE, "w", encoding="utf-8") as licenseFile:
            licenseFile.write(decodedLicense.decode("utf-8"))
    except Exception as e:
        print("Error while reading supplied ARCION_LICENSE (did you Base64 encode it?)")
        sys.exit(1)

copytree("/libs", "/arcion/release/arcion-on-premises/core/lib")

cmd = ["supervisord", "-c", "/etc/supervisord.conf"]
p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
for line in p.stdout:
    print(line)
p.wait()

sys.exit(p.returncode)
