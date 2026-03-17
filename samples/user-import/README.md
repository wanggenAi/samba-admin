# Legacy TXT Import Samples

This folder contains sample files for `POST /api/users/import`.

## Files

- `group-ms-63_24.txt`
- `group-pe-24.txt`
- `group-ii-2025.txt`

## Expected format

1. The file must contain a group marker line `группа CODE-NUMBER` (case-insensitive), for example:
   - `группа МС-63/24`
2. Each user block should use this structure:
   - optional ordinal line: `1.` / `18.` / `25)`
   - required full name line (Russian letters + spaces):
     - `Иванов Иван`
     - `Петров Петр Сергеевич`
   - optional paid marker line:
     - `$`  -> imported as `paid_flag="$"` (`employeeType="$"`)
   - optional student id line (digits only), for example:
     - `230385`
3. If student id is missing, the user is still created and `employeeID` is left empty.

## Notes

- Keep files as UTF-8 text.
- One file represents one study group batch.
- Default import limits:
  - max `2 MB` per file
  - max `10 MB` total upload size
