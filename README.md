# Generate production data packages for EMS

This action packages existing KiCad jobset exports and uploads one ZIP per assembly/coating combination to the same GitHub release. It does not run KiCad: export the jobset and commit the production data before creating the release.

## Production data layout

The repository root must contain a `*-prod` directory, for example:

```text
IOU16-prod/
├── pcb/
│   ├── IOU16-01-Gerber/       # Gerbers, drill data, .gbrjob and Coat Gerbers
│   └── pcb-datasheet.pdf
├── assembly/
│   ├── A/
│   │   ├── BOMs/IOU16-01A_BOM.csv
│   │   ├── BOMs/IOU16-01A_BOM_parts.csv
│   │   └── ...position, assembly PDFs, STEP, renderings
│   └── B/
│       └── ...corresponding variant data
├── coating/
│   ├── IOU16-01-coating-top.pdf
│   └── IOU16-01-coating-bottom.pdf
├── documentation/            # not included in EMS packages
└── IOU16-01-odb++.zip         # optional; included when present
```

The project name comes from the production folder (`IOU16-prod` → `IOU16`), independently of the repository name (`hw-iou16`, for example). Release tags use `<hardware revision>.<release version>`: `03.0` is the first release of hardware revision `03`, `03.1` the next release of the same hardware. Only the first component is used to match the KiCad exports; leading zeros are preserved. Three-component tags such as `03.0.0` and an optional `v` prefix are also accepted for compatibility. Prerelease and build suffixes are accepted. Other tags (for example `03` or `R03`) are used as-is. The upload still targets the original release tag. Each direct child directory of `assembly/` must be a unique single-letter variant (case insensitive). Its files are included recursively. Each variant must contain `<Project>-<Revision><Variant>_BOM.csv`; a missing or excluded BOM fails the build, including when the hardware revision derived from the release tag does not match the exported revision. The old layout with BOMs directly under `assembly/` is not supported.

If there are several `*-prod` directories, exactly one folder name must contain the release revision (case insensitive). Otherwise the build fails.

## Package contents and naming

ZIP names are `<Project>-<Revision><Variant>[Z]-<YYYYMMDDHHMM>-ems.zip`, with one UTC timestamp shared by all packages of a run.

Each package preserves the production folder and its subdirectories and includes:

- `pcb/` recursively, excluding Coat Gerbers in every package. Removed coating-layer references are also filtered out of `.gbrjob` indexes inside the ZIP; source files remain unchanged.
- Exactly one `assembly/<Variant>/` directory, including its BOMs and assembly outputs.
- The matching `<Project>-<Revision>-odb++.zip` at the production folder root, if present. ODB++ contents are copied unchanged.
- `coating/` recursively, only in packages with suffix `Z`.

Coat Gerbers are detected recursively under `pcb/`: filenames contain `Coat` and have extension `.gbr`, `.ger`, or `.gerber`, case insensitive. If found, both coated and uncoated packages are generated for every variant. `coating/` must then contain at least one non-excluded file. Without Coat Gerbers, only uncoated packages are generated, even if a `coating/` folder exists.

`documentation/`, schematic sources, cost reports and all other repository files are not packaged. Files matching the global exclusions are also omitted.

For variants A and B with coating data, release tag `01` produces:

```text
IOU16-01A-202610081200-ems.zip
IOU16-01AZ-202610081200-ems.zip
IOU16-01B-202610081200-ems.zip
IOU16-01BZ-202610081200-ems.zip
```

## Inputs

- `exclude-patterns`: Optional whitespace-separated glob patterns, matched case insensitively against each original `./`-relative repository path. `*` also matches path separators, as with Python `fnmatch`. Excluding all PCB Gerbers, a required BOM, or all coating files when Coat Gerbers exist fails the build.
- `access-token`: Token with access to the repository/submodules and permission to upload release assets.

`include-patterns` and `rclone-params` are not supported. This action uploads to GitHub releases; it does not copy files to SharePoint.

## Usage

```yaml
on:
  release:
    types: [published]

jobs:
  ems-package:
    runs-on: ubuntu-latest
    name: Build EMS Packages
    steps:
      - uses: ci4rail/ems-package-action@v1
        with:
          access-token: ${{ secrets.HW_CI_TOKEN }}
```

The updated implementation must be available at the action version referenced by the caller. Local edits alone do not change the published `@v1` action.

## Validation

Run the packaging integration tests locally:

```sh
python3 -m unittest discover -s tests -v
```

## Migrating callers from the old v1 implementation

The original `v1` tag points to the implementation that creates a single repository ZIP. This variant-aware implementation must be published and the caller must reference its commit or an updated release tag. Updating `main` alone does not move `v1`.

For example, a release tagged `03.0` with production files named `IOUB3-03A_BOM.csv` and `IOUB3-03B_BOM.csv` produces packages named `IOUB3-03A-…`, `IOUB3-03AZ-…`, `IOUB3-03B-…`, and `IOUB3-03BZ-…`.
