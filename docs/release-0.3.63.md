# Sonicprobe 0.3.63

On Unix, `helpers.file_w_tmp(lines, path)` stages writes beside the named target
and syncs the new file before renaming it. Readers see the old file until the
replacement is complete, including when the system temporary directory is on
a different filesystem. Replacements preserve owner, group and permission bits.
Failed writes clean up the temporary file and preserve the original target.

Calls without a destination still return a temporary filename for the caller to
remove. Calls with a directory still place a generated file in that directory.

Install with `python -m pip install --upgrade 'sonicprobe==0.3.63'`.
