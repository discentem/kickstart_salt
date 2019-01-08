# pylint: disable=C0111
#!/usr/bin/python
from kickstart_salt_imports import *

# Borrowed some code from
#  https://github.com/facebook/IT-CPE/blob/master/chef/tools/chef_bootstrap.py

class GCEMetadataWrapper:
    '''Wrapper class for retrieving Instance & Project Metadata'''
    @staticmethod
    def return_request(request):
        '''Returns Get request if status code is 200; others returns None'''
        if request.status_code == 200:
            return request.content.decode('utf-8')
        return None

    def get_metadata_value(self, url):
        '''Executes Get request against GCP Metadata server with proper headers'''
        try:
            request = requests.get(url, headers={"Metadata-Flavor":"Google"})
        except requests.exceptions.ConnectionError as err:
            print(err, end="\n\n")
            print("This is likely not a GCE server.")
            exit(1)
        return self.return_request(request)

    def get_instance_metadata_value(self, key):
        '''Helper method for retrieving Instance Metadata values'''
        url = "http://metadata.google.internal/computeMetadata/v1/instance/{0}"
        url = url.format(key)
        return self.get_metadata_value(url)

    def get_project_metadata_value(self, key):
        '''Helper method for retrieving Project Metadata values'''
        url = "http://metadata.google.internal/computeMetadata/v1/project/{0}"
        url = url.format(key)
        return self.get_metadata_value(url)

    def get_any_metadata_value(self, key, default=None):
        '''
        Helper method for retrieving either instance metadata, if it exists,
        or project metadata. If metadata can't be found for the passed key in
        either instance or project metadata, the value of default is returned.
        '''
        instance_metadata_value = self.get_instance_metadata_value(key)
        project_metadata_value = self.get_project_metadata_value(key)
        if instance_metadata_value is None:
            if project_metadata_value is None:
                return default
            return project_metadata_value

        return instance_metadata_value

# pylint: disable=R0902
class KickstartSalt:
    '''A class to kickstart bootstrap-salt.sh!'''
    @staticmethod
    def filter_by(data, attr=platform.system()):
        try:
            return data[attr]
        except KeyError:
            print("No value is defined for data['{0}']".format(attr))
            exit(1)
            
    # pylint: disable=R0913
    def __init__(self,
                 dns_entries=None,
                 bootstrap_salt_save_path=None,
                 bootstrap_salt_expected_hash=None,
                 bootstrap_salt_hash_type=(
                    self.filter_by(
                        {"Windows":"md5",
                         "Linux":"sha256"
                        },
                        platform.system()
                    )
                 ),
                 bootstrap_salt_json_args=None,
                 etc_salt_master_d=None,
                 salt_master_autosign_patterns=None,
                 salt_master_prerequisite_yum_packages=None,
                 bootstrap_salt_download_url=None):

        # Setting up object instance variables
        self.dns_entries = dns_entries
        self.bootstrap_salt_save_path = bootstrap_salt_save_path
        self.bootstrap_salt_expected_hash = bootstrap_salt_expected_hash
        self.bootstrap_salt_hash_type = bootstrap_salt_hash_type
        self.bootstrap_salt_json_args = bootstrap_salt_json_args
        self.etc_salt_master_d = etc_salt_master_d
        self.salt_master_autosign_patterns = salt_master_autosign_patterns
        self.salt_master_prerequisite_yum_packages = salt_master_prerequisite_yum_packages
        self.bootstrap_salt_download_url = bootstrap_salt_download_url

        # Run the bootstrap!!
        self.run_bootstrap()

    def run_bootstrap(self):
        '''
        Main bootstrapping function. Program flow is defined here. Meat and
        potatoes.
        '''
        operating_system = platform.system()
        if operating_system == 'Linux':
            # Write array of DNS entries to resolv.conf
            self.set_dns_linux(self.dns_entries)
            # set the shell to "sh" because we are on linux
            shell = "sh"
            # pylint: disable=C0301
            # '-M' and '-J' signify that we are bootstrapping a master as per
            #  https://docs.saltstack.com/en/latest/topics/tutorials/salt_bootstrap.html#command-line-options

            # so... if we are, do master specific bootstrapping things...
            if '-M' in self.bootstrap_salt_json_args:
                if not os.path.isdir("/root/.ssh/"):
                    os.mkdir('/root/.ssh')

                pathlib.Path("/etc/salt/master.d").mkdir(parents=True,
                                                         exist_ok=True)
                self.write_etc_salt_master_d_conf(
                    etc_salt_master_d=self.etc_salt_master_d
                )
                self.write_autosign_conf(patterns=self.salt_master_autosign_patterns)
                # Install prereq yum packages.
                self.install_yum_packages(packages=self.salt_master_prerequisite_yum_packages)

        elif operating_system == "Windows":
            self.set_dns_windows(self.dns_entries)
            shell = "powershell"

        else:
            msg = "{0} is not a supported platform of kickstart-salt.py"
            formatted_msg = msg.format(operating_system)
            print(formatted_msg)
            exit(1)

        # download and save the bootstrap script from upstream.
        bootstrap_path = self.download_salt(url=self.bootstrap_salt_download_url,
                                            save_path=(self.bootstrap_salt_save_path))
        # verify hash of upstream bootstrap
        if self.hash_matches(file_path=bootstrap_path,
                             hash_type=self.bootstrap_salt_hash_type,
                             expected_hash=self.bootstrap_salt_expected_hash):

            print(bootstrap_path + " hash matches bootstrap_salt_expected_hash.")
            cmd = [shell, bootstrap_path]

            # Munge the bootstrap args into normal CLI flags that are valid for
            #  the upstream bootstrap script
            cmd.extend(self.process_bootstrap_salt_json_args(self.bootstrap_salt_json_args))

            # Finally, run the damn thing!
            run_bootstrap = self.run_live(cmd)
            if run_bootstrap != 0:
               # if the script exits anything but zero, output exit code and exit
                print(run_bootstrap)
                exit(1)
        else:
            print(bootstrap_path + " hash does not match bootstrap_salt_expected_hash!")

    @staticmethod
    def write_autosign_conf(patterns=None):
        '''
        Takes a list of strings, which represent salt master autosign patterns
        and writes it to /etc/salt/autosign.conf.
        '''
        if patterns is not None:
            if not os.path.isdir("/etc/salt"):
                os.mkdir('/etc/salt/')
            with open('/etc/salt/autosign.conf', 'w+') as autosign_conf:
                for pattern in patterns:
                    autosign_conf.write(pattern + '\n')

    @staticmethod
    def write_etc_salt_master_d_conf(etc_salt_master_d):
        for conf_name, json_conf in etc_salt_master_d.items():
            # print(conf_name)
            # print(json_conf)
            # print("conf_name type: " + str(type(conf_name)))
            # print("json_conf type: " + str(type(conf_name)))
            conf_file_path = "/etc/salt/master.d/{0}".format(conf_name)
            with open(conf_file_path, 'w') as file_object:
                yaml.dump(json_conf, file_object, default_flow_style=False)

    def set_dns_windows(self, dns_entries):
        '''Use powershell to set DNS'''
        if dns_entries is None:
            logging.warning("dns_entries not provided.")
        elif len(dns_entries) > 2:
            print("Info: dns_entries has more than 2 entries.", end=' ')
            print("Windows will only utilize the first 2 entries.")

        dns_entries_with_quotes = []
        for entry in dns_entries[0:2]:
            # As far as I know, Windows can only use up to 2 dns entries, so
            #  that's why we do dns_entries[0:2]. At the very least, this current
            #   powershell call only supports up to 2 dns entries
            dns_entries_with_quotes.append("\'{0}\'".format(entry))
        dns_entries_pwsh_array = ', '.join(dns_entries_with_quotes)
        cmd = ["powershell", "Set-DnsClientServerAddress", "-InterfaceAlias", "\"Ethernet\"",
               "-serverAddresses", "@(" + dns_entries_pwsh_array + ")"]
        set_dns_return_code = self.run_live(cmd)
        if set_dns_return_code != 0:
            print(set_dns_return_code)
            exit(1)

    @staticmethod
    def set_dns_linux(dns_entries):
        '''Write dns_entries to /etc/resolv.conf'''
        if dns_entries is None:
            raise ValueError("dns_entries can't be None")
        with open('/etc/resolv.conf', 'w') as conf:
            for item in dns_entries:
                conf.write("{0}\n".format(item))

    @staticmethod
    def download_salt(url, save_path):
        # pylint: disable=C0301
        # Borrowed from https://github.com/facebook/IT-CPE/blob/master/chef/tools/chef_bootstrap.py#L305
        '''
        Generic function to download a file to a place on disk. For our
        purposes we will use it to download the upstream Salt
        bootstrap-salt.sh or bootstrap-salt.ps1
        '''
        if url is None:
            raise ValueError("url can't be None")
        if save_path is None:
            raise ValueError("save_path can't be None")


        # pylint: disable=W0106
        print("Downloading from {0}...".format(url), end='')
        sys.stdout.flush()
        try:
            # handles redirects
            actual_url = urllib.urlopen(url).geturl()

            # pylint: disable=C0103
            with open(save_path, 'wb') as f:
                f.write(urllib.urlopen(actual_url).read())
            if os.path.exists(save_path):
                print('success.')
                return save_path
        except urllib.URLError:
            print("failed! Unable to download from %s!" % url)
      # If we're here, we got nothing.
        return None

    @staticmethod
    def hash_matches(file_path,
                     hash_type,
                     expected_hash):
        '''
        Check if a file matches an expected sha256 or md5 hash
        '''
        lvars = {
            'file_path': file_path,
            'hash_type': hash_type,
            'expected_hash': expected_hash
        }

        for key, val in lvars.items():
            if val is None:
                raise ValueError("{0} can't be None".format(key))

        # if file_path is None:
        #     raise ValueError("file_path can't be None")
        # if hash_type is None:
        #     raise ValueError("hash_type can't be None")
        # if expected_hash is None:
        #     raise ValueError("expected_hash can't be None")
        try:
            h = getattr(hashlib, hash_type)()
        except AttributeError:
            msg = "{0} is not a valid hash type."
            raise AttributeError(msg.format(hash_type))

        with open(file_path, 'rb', buffering=0) as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)

        return h.hexdigest() == expected_hash

    @staticmethod
    def process_bootstrap_salt_json_args(jsondict):
        '''
        Gathers arguments from a json string and munge them into valid CLI
        flags bootstrap-salt.sh or bootstrap-salt.ps1.
        '''
        if jsondict is None:
            raise ValueError("jsondict can't be None")

        args = []
        # special keys which signify which salt release to install
        install_types = ['stable', 'daily', 'testing', 'git']

        # args that must go at the end
        end_args = {}

        #print(jsondict)
        for key, val in jsondict.items():
            #key = key.encode('utf-8')
            if key in ['-j', '-J']:
                args.extend([key, json.dumps(val)])
            # ignore install_types for now:
            #  these MUST be last when passed to bootstrap-salt.sh!
            elif key in install_types:
                end_args[key] = val
            else:
                ext = [key]
                # if val is not None or ""
                if val:
                    ext.append(val)
                args.extend(ext)

        for key, val in end_args.items():
            ext = [key]
            # if val is not None or ""
            if val:
                ext.append(val)
            args.extend(ext)

        return args

    @staticmethod
    def run_live(command):
        """
        Run a subprocess with real-time output.
        Can optionally redirect stdout/stderr to a log file.
        Returns only the return-code.
        """
      # Validate that command is not a string
        # if isinstance(command, basestring):
        if isinstance(command, str):
        # Not an array!
            raise TypeError('Command must be an array')
        # Run the command
        if platform.system() == "Windows":
            proc = subprocess.Popen(command,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    shell=True)
        else:
            proc = subprocess.Popen(command,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
        while proc.poll() is None:
            # pylint: disable=C0103
            l = proc.stdout.readline()
            # pylint: disable=W0106
            # We need to keep the trailing comma tuple because, for
            #  some reason it makes the live output much cleaner.
            # pylint: disable=R1707
            print(l.decode('utf-8'), end=''),
        print(proc.stdout.read())
        return proc.returncode

    def install_yum_packages(self, packages=None):
        '''
        Installs a list of packages via Yum
        '''
        if packages is not None:
            # packages_list = packages.split(',')
            cmd_string = "sudo yum install {0} -y"
            cmd = cmd_string.format(' '.join(packages))
            install_yum_packages = self.run_live(cmd.split(' '))
            if install_yum_packages != 0:
                print(install_yum_packages)
                exit(1)

class KickstartSaltGoogleComputeEngine(KickstartSalt):

    @staticmethod
    def validate_and_parse_json(json_string, description=""):
        # if we get none here, just return
        if json_string is None:
            return None
        try:
            return json.loads(json_string)
        except json.decoder.JSONDecodeError as err:
            err_list = (err.doc).split('\n')
            RED = "\033[1;31m"
            RESET = "\033[0;0m"
            # pylint: disable=C0301
            print("kickstart-salt has crashed while try to parse the json block described as: {0}. ".format(description), end='\n\n')
            print("We've tried to highlight a line which ", end='')
            print("is close to the error, though the highlighting may be ", end='')
            print("a few lines off." + '\n')
            print(">>> Error: ", end='')
            print(err)
            for line in err_list:
                if err_list.index(line) == int(err.lineno)-1:
                    sys.stdout.write(RED)
                    print(line)
                    sys.stdout.write(RESET)
                    continue

                print(line)
            exit(1)


    def generate_dns_entries(self):
        dns_project_metadata = self.gce_metadata.get_project_metadata_value(
            "attributes/dns"
        )

        # attempt to parse JSON into dict only if dns_project_metadata is not None
        if dns_project_metadata:
            dns_project_metadata = (
                self.validate_and_parse_json(
                    dns_project_metadata,
                    description="'dns' key in project metadata"
                )
            )

        # attempt to parse JSON into dict only if dns_instance_metadata is not None
        dns_instance_metadata = self.gce_metadata.get_instance_metadata_value(
            "attributes/dns"
        )
        if dns_instance_metadata:
            dns_instance_metadata = (
                self.validate_and_parse_json(
                    dns_instance_metadata,
                    description="'dns' key in instance metadata"
                )
            )

        if dns_project_metadata and dns_instance_metadata:
            dns_metadata = deep_merge.merge(
                dns_project_metadata,
                dns_instance_metadata
            )
        elif dns_project_metadata and (dns_instance_metadata is None):
            dns_metadata = dns_project_metadata
        elif dns_instance_metadata and (dns_project_metadata is None):
            dns_metadata = dns_instance_metadata
        else:
            logging.warning("dns_project_metadata and dns_instance_metadata are both none.")

        if platform.system() == "Windows":
            return dns_metadata['entries']
        else:
            project_id = self.gce_metadata.get_project_metadata_value(
                "project-id"
            )
            dns_list = [
                "search c.{0}.internal google.internal".format(project_id)
            ]
            for entry in dns_metadata['entries']:
                dns_list.append('nameserver {0}'.format(entry))

            dns_list.append("nameserver 169.254.169.254")

        return dns_list

    def __init__(self):
        self.gce_metadata = GCEMetadataWrapper()
        self.dns_entries = self.generate_dns_entries()
        # pylint: disable=C0103
        pp = pprint.PrettyPrinter(indent=2)

        self.kickstart_salt_args_instance_metadata = (
            self.validate_and_parse_json(
                self.gce_metadata.get_instance_metadata_value(
                    "attributes/kickstart_salt_args"
                )
            )
        )
        print("kickstart_salt_args_instance_metadata:")
        pp.pprint(self.kickstart_salt_args_instance_metadata)
        print('\n\n')

        self.kickstart_salt_args_project_metadata = (
            self.validate_and_parse_json(
                self.gce_metadata.get_project_metadata_value(
                    "attributes/kickstart_salt_args"
                )
            )
        )
        print("kickstart_salt_args_project_metadata:")
        pp.pprint(self.kickstart_salt_args_project_metadata)
        print('\n\n')

        print("kickstart_salt_args:\n")
        if self.kickstart_salt_args_instance_metadata and self.kickstart_salt_args_project_metadata:
            self.kickstart_salt_args = deep_merge.merge(
                self.kickstart_salt_args_project_metadata,
                self.kickstart_salt_args_instance_metadata
            )
        elif self.kickstart_salt_args_instance_metadata and (self.kickstart_salt_args_project_metadata is None):
            self.kickstart_salt_args = self.kickstart_salt_args_instance_metadata
        elif self.kickstart_salt_args_project_metadata and (self.kickstart_salt_args_instance_metadata is None):
            self.kickstart_salt_args = self.kickstart_salt_args_instance_metadata
        else:
            raise ValueError("kickstart_salt_args_instance_metadata and kickstart_salt_args_project_metadata are both None. This can't be.")

        pp.pprint(self.kickstart_salt_args)

        KickstartSalt.__init__(self,
                               dns_entries=self.dns_entries,
                               bootstrap_salt_save_path=(
                                   self.kickstart_salt_args.get(
                                       "bootstrap_salt_save_path_{0}".format(platform.system()),
                                       # default value:
                                       self.kickstart_salt_args.get(
                                           "bootstrap_salt_save_path",
                                           self.filter_by(
                                               {"Windows": "c:\\bootstrap-salt.ps1",
                                                "Linux": "/tmp/bootstrap-salt.sh"
                                               },
                                               platform.system()
                                           )
                                       )
                                   )
                               ),
                               bootstrap_salt_expected_hash=(
                                   self.kickstart_salt_args.get(
                                       'bootstrap_salt_expected_hash',
                                       None
                                   )
                               ),
                               bootstrap_salt_hash_type=(
                                   self.kickstart_salt_args['bootstrap_salt_hash_type']
                               ),
                               bootstrap_salt_json_args=(
                                   self.kickstart_salt_args['bootstrap_salt_json_args']
                               ),
                               etc_salt_master_d=(
                                   self.kickstart_salt_args.get(
                                       '/etc/salt/master.d/',
                                       None)
                               ),
                               salt_master_autosign_patterns=(
                                   self.kickstart_salt_args.get(
                                       'salt_master_autosign_patterns',
                                       None
                                   )
                               ),
                               salt_master_prerequisite_yum_packages=(
                                   self.kickstart_salt_args.get(
                                       "salt_master_prerequisite_yum_packages",
                                       None
                                   )
                               ),
                               bootstrap_salt_download_url=(
                                   self.kickstart_salt_args.get(
                                       "bootstrap_salt_download_url_{0}".format(platform.system()),
                                       # default value:
                                       self.kickstart_salt_args.get(
                                           "bootstrap_salt_download_url",
                                           self.filter_by(
                                               # pylint: disable=C0301
                                               {'Windows': "https://raw.githubusercontent.com/saltstack/salt-bootstrap/e1cb060e655c564cecb857f179e0656ff8faf784/bootstrap-salt.ps1",
                                                'Linux': "https://bootstrap.saltstack.com"
                                               },
                                               platform.system()
                                           )
                                       )
                                   )
                               )
                              )

        # self.disable_firewalld()
        # self.disable_selinux()

if __name__ == '__main__':
    KickstartSaltGoogleComputeEngine()
