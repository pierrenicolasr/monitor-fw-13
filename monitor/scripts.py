
import os
import click
import shutil
import subprocess
import pkg_resources
import sys
import errno

from monitor.logs import init_logging, logger

class ValidationExceptionCannotParseFileWaveVersion(Exception):
    pass


class ValidationExceptionWrongFileWaveVersion(Exception):
    pass


class NotRunningRoot(Exception):
    pass


@click.group()
def cli():
    click.echo("FileWave Monitor v13 configuration.")


delay_30m = 60 * 30


def run_root_command(cmd_array):
    try:
        os.rename('/etc/foo', '/etc/bar')
    except IOError as e:
        if (e == errno.EPERM):
            return False

    proc = subprocess.Popen(cmd_array, stdout=subprocess.PIPE)
    return proc.communicate()[0].decode('utf-8')

def run_root_commands(commands):
    for c in commands:
        run_root_command(c)

def running_on_a_fwxserver_host(exist_func=os.path.exists):
    '''
    Check directories exist to see if we are running on a FileWave server host installation
    This should return True if we are, regardless of being Mac/Linux/Docker etc.
    '''
    dirs_that_must_exist = ["bin", "certs",
                            "django", "log"]
    main_filewave_dir = os.path.join("/usr/local", "filewave")
    if not exist_func(main_filewave_dir):
        return False
    for f in [os.path.join(main_filewave_dir, d) for d in dirs_that_must_exist]:
        if not exist_func(f):
            return False
    return True


@cli.command('integrate', help="Integrates the module assuming you are running this on the FileWave Server")
def install_into_environment():
    init_logging()

    if running_on_a_fwxserver_host():
        if run_root_command(["ls", "-l"]) is False:
            logger.info(
                "provisioning is requested - but I've detected you are not running as root - aborting")
            raise NotRunningRoot(
                "provisioning is requested - but I've detected you are not running as root - aborting")

        try:
            provision_postgres_wal_interval()
            provision_apache_mod_status()
            provision_mtail_binary()
            provision_exporters()
            provision_supervisord_conf()

            logger.info("Looks like everything is configured, now restart the server: /usr/local/filewave/python/supervisordctl reload")

        except Exception as e:
            logger.error(
                "Error during provisioning, are you using sudo?")
            logger.error(e)
            return
    else:
        logger.info("Didn't detect a FileWave Server host - configuration aborted")

def provision_postgres_wal_interval():
    # /usr/local/filewave/fwxserver/DB/pg_data/postgresql.conf
    # log_min_duration_statement = 200
    #
    cmds = [
        "sed -i 's/log_min_duration_statement = 1000/log_min_duration_statement = 200/g' /usr/local/filewave/fwxserver/DB/pg_data/postgresql.conf"
    ]

    return run_root_commands(cmd)

def provision_apache_mod_status():
    '''
    #LoadModule status_module modules/mod_status.so

    # Uncomment following lines to enable mod status = and connect to https://localhost:20443/server-status?refresh=5 to see server status     
    # Used by the prometheus apache_exporter. Works only on localhost (intentional to reduce security exposure).                               
    <IfModule status_module>                                                                                                                   
        <Location /server-status>                                                                                                              
            SetHandler server-status                                                                                                           
            Order Deny,Allow                                                                                                                   
            Deny from all                                                                                                                      
            Allow from 127.0.0.1 ::1                                                                                                           
        </Location>                                                                                                                            
        ExtendedStatus On                                                                                                                      
    </IfModule>                                                                                                                                
    '''
    cmds = [
        "sed -i 's/#LoadModule status_module modules\/mod_status\.so/LoadModule status_module modules\/mod_status\.so/g' /usr/local/filewave/apache/conf/httpd.conf"
    ]

    run_root_commands(cmds)

def provision_mtail_binary():
    # mtail binary: 15th Jul 2020
    # https://github.com/google/mtail/releases/download/v3.0.0-rc36/mtail_v3.0.0-rc36_linux_amd64
    cmds = [
        "mkdir -p /usr/local/etc/filewave/mtail/progs",
        "chown -R root:root /usr/local/etc/filewave/mtail",
        "wget https://github.com/google/mtail/releases/download/v3.0.0-rc36/mtail_v3.0.0-rc36_linux_amd64 -o /usr/local/sbin/mtail",
        "chmod +x /usr/local/sbin/mtail"
    ]

    run_root_commands(cmds)

    # write .mtail programs into /usr/local/etc/filewave/mtail/progs
    for mtail_file in pkg_resources.resource_listdir("monitor", "config"):
        if yaml_file.endswith(".mtail"):
            data = pkg_resources.resource_string("monitor.config", yaml_file)
            provisioning_file = os.path.join("/usr/local/etc/filewave/mtail/progs", yaml_file)
            with open(provisioning_file, 'wb') as f:
                f.write(data)
            shutil.chown(provisioning_file, user="root", group="root")

def provision_exporters():
    logger.info("downloading postgres exporter...")
    # from https://github.com/wrouesnel/postgres_exporter/releases/download/v0.8.0/postgres_exporter_v0.8.0_linux-amd64.tar.gz
    cmds = [
        "wget https://github.com/wrouesnel/postgres_exporter/releases/download/v0.8.0/postgres_exporter_v0.8.0_linux-amd64.tar.gz",
        "tar xzf postgres_exporter_v0.8.0_linux-amd64.tar.gz",
        "mv -f postgres_exporter_v0.8.0_linux-amd64/postgres_exporter /usr/local/sbin/ && rm -rf postgres_exporter_v0.8.0_linux-amd64"
    ]

    run_root_commands(cmds)

    logger.info("downloading apache exporter...")
    cmds = [
        "wget https://github.com/Lusitaniae/apache_exporter/releases/download/v0.8.0/apache_exporter-0.8.0.linux-amd64.tar.gz",
        "tar xzf apache_exporter-0.8.0.linux-amd64.tar.gz",
        "mv -f apache_exporter-0.8.0.linux-amd64/apache_exporter /usr/local/sbin/ && rm -rf apache_exporter-0.8.0.linux-amd64"
    ]

    run_root_commands(cmds)

    logger.info("downloading node_exporter")
    cmds = [
        "wget https://github.com/prometheus/node_exporter/releases/download/v1.0.1/node_exporter-1.0.1.linux-amd64.tar.gz",
        "tar xzf node_exporter-1.0.1.linux-amd64.tar.gz",
        "mv -f node_exporter-1.0.1.linux-amd64/node_exporter /usr/local/sbin/ && rm -rf node_exporter-1.0.1.linux-amd64"
    ]

def provision_supervisord_conf():
    cmds = [
        "sed -i 's/\;files = relative\/directory\/\*\.ini/extras\/\*\.conf/g' /usr/local/etc/filewave/supervisor/supervisord-server.conf",
        "sed -i 's/\; port\=\*\:9001/port=127\.0\.0\.1\:9001/g' /usr/local/etc/filewave/supervisor/supervisord-server.conf",
        "sed -i 's/\; \[inet_http_server\]/\[inet_http_server\]/g' /usr/local/etc/filewave/supervisor/supervisord-server.conf"
    ]

    supervisord_dir = os.path.join("/usr/local/etc/filewave/supervisor/", "extras")
    if not os.path.exists(supervisord_dir):
        os.makedirs(supervisord_dir)

    data = pkg_resources.resource_string("monitor.config", "monitor-v13.conf").decode('utf-8')
    provisioning_file = os.path.join(supervisord_dir, "monitor-v13.conf")
    with open(provisioning_file, "w+") as f:
        f.write(data)

    run_root_commands(cmds)

'''
def provision_prometheus_scrape_configuration():
    prometheus_dir = os.path.join(
        "/usr/local/etc/filewave/prometheus/conf.d/jobs", "http")
    if not os.path.exists(prometheus_dir):
        logger.error(
            f"The Prometheus directory ({prometheus_dir}) does not exist; is this version 14+ of FileWave?")
        return

    for yaml_file in pkg_resources.resource_listdir("extra_metrics", "cfg"):
        if yaml_file.endswith(".yml"):
            data = pkg_resources.resource_string(
                "extra_metrics.cfg", yaml_file)
            provisioning_file = os.path.join(prometheus_dir, yaml_file)
            with open(provisioning_file, 'wb') as f:
                f.write(data)
            prov_owner = platform.get_web_username()
            shutil.chown(provisioning_file, user=prov_owner, group=prov_owner)

'''