## Zaod OS Phase 2 kernel report

- Date (UTC): 2026-11-15T11:10:36Z
- Kernel release: `6.18.63-zaod`
- Source archive: Linux 6.18.63, verified in [versions.md](../versions.md)
- Build host: Linux x86_64 Codespaces, 2 CPU cores

## Validation

- Kernel config validator: PASS (`tests/check_kernel_config.py`)
- ShellCheck and Bash syntax: PASS
- Ruff: PASS
- QEMU initramfs boot: PASS; kernel reached `Run /init as init process`, remained alive through the controlled 20-second timeout, and reported no panic or init execution error.
- Kernel build log: `build/out/kernel/build.log`

## Artifacts

- Kernel image: `build/out/kernel/vmlinuz` (13 MB)
  - SHA256: `faa01aece46c5df2164698cf48d842dc49b44f25d7841af504ebb6976b81faef`
- Kernel config: `build/out/kernel/config` (149 KB)
  - SHA256: `0229c20c06b51fcfdba5481dcce18f2eeee58dafe6f898e9d94f59af3260c422`
- Modules archive: `build/out/kernel/modules.tar.gz` (9.0 MB)
  - Includes `modules.dep` for `6.18.63-zaod`
  - SHA256: `7e810822807411afab888ab7d03f911e06cda604cb5ff86e07ce2e12f2a503d1`
- System map: `build/out/kernel/System.map` (7.3 MB)
  - SHA256: `2ff6a666b1ee10f0b9c887f793e3b07e73019fa9044826824c9a86fccbc0ffc1`

## Build reliability

- Kernel builds are serialized using `build/out/kernel/build.lock` to prevent concurrent make processes from racing on shared objects.
- `CLEAN_BUILD=0` resumes an interrupted build without removing completed objects.
- The build host needs `kmod` for `depmod` and a valid modules archive; module installation errors are no longer suppressed.
