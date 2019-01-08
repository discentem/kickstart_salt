<!-- [![CircleCI](https://circleci.com/gh/discentem/kickstart-salt.svg?style=svg)](https://circleci.com/gh/discentem/kickstart-salt)

[![AppVeyor](https://ci.appveyor.com/api/projects/status/github/discentem/kickstart-salt?svg=true)](https://ci.appveyor.com/project/discentem/kickstart-salt) -->

## What is kickstart-salt.py?

`kickstart-salt.py` is a fancy wrapper around [bootstrap-salt.sh](https://github.com/saltstack/salt-bootstrap/blob/stable/bootstrap-salt.sh) and [bootstrap-salt.ps1](https://github.com/saltstack/salt-bootstrap/blob/stable/bootstrap-salt.ps1) for bootstrapping Salt minions (Centos and Windows Server) and masters (Centos).

Right now it only supports doing this in Google Compute Engine, but it should be easily extensible to other cloud platforms.

### High Level Overview
`kickstart-salt.py` will perform the following tasks on Centos and Windows Server, with arguments retrieved from [Google Compute Engine Instance metadata](https://cloud.google.com/compute/docs/storing-retrieving-metadata):

1. Sets up DNS servers in `/etc/resolv.conf` or via `Set-DnsClientServerAddress`
2. Optionally creates an [`autosign_file`](https://docs.saltstack.com/en/latest/ref/configuration/master.html#autosign-file) if bootstrapping a salt master
3. Optionally installs any list of yum packages on the Salt Master
    * This functionally was included particularly to install `git` and `python-pygit2`, which are prerequisites for [gitfs](https://docs.saltstack.com/en/latest/topics/tutorials/gitfs.html) on the Salt Master.
    * Even if you specify a list of yum packages while bootstrapping a minion, the packages will not be installed. This functionally is restricted to only run on the Salt Master. If you need to install packages on a salt minion, use salt ;P
4. Downloads upstream bootstrap-salt script
    * The url is configurable so you can pin to a specific version of the upstream bootstrap script or host it internally for additional security.
5. Verifies the md5 or sha256 hash of the upstream bootstrap-salt script.
6. Parses bootstrap-salt arguments, provided as json, into the normal cli flags expected by the upstream bootstrap-salt script. Any argument/parameter that is valid for the upstream script can be passed via `kickstart-salt.py` as a key/value pair. See the Usage section for more details.

#### Building a binary with pyinstaller
We can use Pyinstaller to produce a portable binary of kickstart-salt.py. With a binary, you don't have to install the python dependencies on each minion and master.

```
/usr/local/bin/pyinstaller /path/to/kickstart-salt.py --onefile
```

### Python dependencies
You'll need to install these dependencies to run or build a functioning copy of kickstart-salt.py. If you intend to build a binary of the script, you only need to install these dependencies on the build machine. If you forgo building a binary, you'll need to install these dependencies on every machine you run kickstart-salt.py on (i.e. every salt minion and salt master)
```bash
yum install python36 -y
python36 -m ensurepip
python36 -m pip install requests
python36 -m pip install pyyaml
python36 -m pip install deep_merge
```

### Usage Guide (Google Compute Engine)

To bootstrap a new Compute Engine VM with kickstart-salt, you just need to provide two Google Compute Engine metadata keys: `startup-script` and `kickstart_salt_args`. You may also optionally provide `dns`.

##### startup-script

`startup-script` is a GCE metadata key documented by Google. You can read more about it here: https://cloud.google.com/compute/docs/startupscript. `startup-script` can be defined at either the instance or project level. The instance level will take precedence.

In the startup-script metadata key, you need to provide a script which downloads and runs kickstart-salt. Here's an example utilizing nexus:

Note: this example assumes you aren't building a binary with PyInstaller. Also contains invalid url for demo purposes. Modify your script to point at a valid url containing the raw file.
```bash
yum install python36 -y
python36 -m ensurepip
python36 -m pip install requests
python36 -m pip install pyyaml
python36 -m pip install deep_merge

curl -k "https://sourcecontrol.co.org/path/to/raw/python/file/kickstart-salt.py" > /tmp/kickstart-salt.py
sudo /usr/bin/python36 /tmp/kickstart-salt.py
```

##### kickstart_salt_args

The final key that kickstart-salt expects is `kickstart_salt_args`, a JSON dictionary. kickstart-salt will deep merge this key's dictionary from project metadata and instance metadata. If a particular key/val exists in both places, instance metadata will take precedence. See https://github.com/halfak/deep_merge for more information on deep merging.

kickstart-salt expects this merged dictionary to have the following keys and values:

<br />

- `bootstrap_salt_expected_hash` *(string), (required)*: sha256 or md5 hash of bootstrap-salt.sh. Type should match `bootstrap_salt_hash_type`.

<br />

- `bootstrap_salt_json_args` *(dictionary), (required)*: keys and values that you would normally provide to bootstrap-salt.sh on the CLI. Any and all arguments that are valid for bootstrap-salt.sh are valid here. See https://github.com/saltstack/salt-bootstrap#bootstrapping-salt) for all of the available arguments. Most arguments are simply passed through to bootstrap-salt.sh without modification from `bootstrap_salt_json_args`, however there are some exceptions:

   If a parameter normally wouldn't have a value, such as `-M`, simply set the value to be an empty string. This is necessary because JSON does not accept keys without values.

   For the other exceptions, check out the code for the `process_bootstrap_salt_json_args` function in kickstart-salt.py.

   Here is an example of `bootstrap_salt_json_args`:

   ```JSON
   {
     "bootstrap_salt_json_args": {
        "stable": "2018.3.2",
        "-M": "",
        "-j": {
          "master": "localhost",
          "grains": {
          }
        }
     }
   }
   ```

<br />

- `bootstrap_salt_hash_type` *(string), (optional)*: must be either `"sha256"` or `"md5"`. Defaults to `"sha256"` on Linux and `"md5"` on Windows if not provided.

<br />

- `salt_master_prerequisite_yum_packages` *(list), (optional)*: list of packages to install before installing salt-master.

<br /><br />

- `bootstrap_salt_save_path_Linux` *(string), (optional)*: full path to the location you want to save bootstrap-salt.sh on Linux hosts. This only applies if `platform.system()` evaluates to `Linux`. If `bootstrap_salt_save_path_Linux` is not defined, bootstrap-salt.sh will be saved at the path defined by the `bootstrap_salt_save_path` key.

<br />

- `bootstrap_salt_save_path_Windows` *(string), (optional)*: full path to the location you want to save bootstrap-salt.sh on Windows hosts. This only applies if `platform.system()` evaluates to `Windows`. If `bootstrap_salt_save_path_Windows` is not defined, bootstrap-salt.ps1 will be saved at the path defined by the `bootstrap_salt_save_path` key.

<br />

- `bootstrap_salt_save_path` *(string), (optional)*: full path to the location you want to save bootstrap-salt.sh or bootstrap-salt.ps1 on the VM. This path is only used if neither `bootstrap_salt_save_path_Linux` nor `bootstrap_salt_save_path_Windows` are defined. If this key itself is not defined, it will default to `c:\bootstrap-salt.ps1` on Windows and `/tmp/bootstrap-salt.sh` on Linux.

<br /><br />

- `/etc/salt/master.d/` *(dictionary), (optional)*: each key in this dictionary represents a file that will be created on-disk inside `/etc/salt/master.d/`. You can have as many keys as you like and you can name each key whatever you want.

  Example `/etc/salt/master.d` keys:
  - `blahblah.conf` *(dictionary)*: the keys and values in this dictionary must simply be valid master config data. Consult https://docs.saltstack.com/en/latest/ref/configuration/master.html. The keys and values inside this dictionary will be written to `/etc/salt/master.d/blahblah.conf` as yaml.
  - `otherthing.conf` *(dictionary)*: same as above. The keys and values inside this dictionary will be written to `/etc/salt/master.d/otherthing.conf` as yaml.

  Here's an example for the `/etc/salt/master.d/` key:

  ```JSON
  {
    "/etc/salt/master.d/": {
      "main.conf": {
        "id": "gcpitsrvsaltmaster",
        "timeout": 12
      },
      "autosign.conf": {
        "autosign_file": "/etc/salt/autosign.conf"
      },
      "fileserver.conf": {
        "fileserver_backend": [
          "gitfs"
        ],
        "gitfs_remotes": [
          {
            "https://sourcecontrol.org.com/salt-repo.git" : [
              { "base": "dev" }
            ]
          },
          {
            "https://sourcecontrol.org.com/salt-repo2.git" : [
              {"base": "develop"},
              {"mountpoint": "salt://salt-repo2"}
            ]
          }
        ]
      },
      "ext_pillar.conf": {
        "ext_pillar": [
          {
            "git": [
              {
                "dev https://sourcecontrol.org.com/salt-pillar.git": [
                  { "env": "base" }
                ]
              }
            ]
          }
        ]
      }
    }
  }
  ```

<br />

##### dns

`dns` can optionally exist as _project metadata key_ or a _instance metadata key_. If it exists in both places, _instance metadata_ will override and take precedence. `dns` should be a valid JSON dictionary with a key called `entries` who's value is a list of (dns) entries. Here's an example of a `dns` JSON blob:

```JSON
{
  "dns": {
    "entries": [
      "127.0.0.1",
      "127.0.0.2"
    ]
  }
}
```
