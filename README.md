# Generate production data package for EMS

This Github action allows you to generate a package from a HW repo contents that can be sent to the EMS.

The package is generated as a ZIP file and added to the release of the github repo. In addition it is written to Ci4Rails Sharepoint folder [Ci4Rail Engineering/EMS-ProdData](https://ci4railcom.sharepoint.com/:f:/s/Ci4RailEngineering/EjZZ_AP1e35AsWEIi2hvI5ABS7LaCczZ1J6yZkw-R_zULg?e=MMReXg). 

The ZIP file is named `<repo-name>-<release-name>-<timestamp>-ems.zip`.

For example, if the repo is named `i101-psu01` and the release is named `01A`, then the package is named `i101-psu01-01A-202201132035-ems.zip`.

In Sharepoint, the package is stored in a subfolder `<repo-name>`.

## Input Variables

* `exclude-patterns`: File patterns to exclude from ZIP file. Patterns must be white space separated. Patterns are `glob` patterns, compared with pythons's `fnmatch` function and are compared against the whole path of each file. Comparisons are case insensitive. Absolute paths always begin with `./`, so the pattern must match this part as well.
* `access-token`: A personal access token that has sufficient rights to read submodule repos and to add files to a release. For example see bitwarden entry `yoda fw-repo-ci`.
* `rclone-params`: rclone configuration parameters for sharepoint upload. Refer to [this confluence page](https://ci4rail.atlassian.net/l/c/yqLP13AN).


## Usage

```yaml
on:
  release:
    types: [published]

jobs:
  ems-package:
    runs-on: ubuntu-latest
    name: Build EMS Package
    steps:
      - uses: ci4rail/ems-package-action@v1
        with:
          exclude-patterns: |
            *.FCStd 
            ./simulation/*
          access-token: ${{ secrets.PAT_TOKEN }}
          rclone-params: ${{ secrets.RCLONE_PARAMS }}
```