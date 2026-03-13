# Legacy TXT Import Samples

This folder contains sample files for `POST /api/users/import`.

## Files

- `group-ms-63_24.txt`
- `group-pe-24.txt`
- `group-ii-2025.txt`

## Expected format

1. A header line containing `Группа CODE-NUMBER` (case-insensitive), for example:
   - `Группа МС-63/24`
2. User lines should contain only Russian letters and spaces:
   - `Иванов Иван`
   - `Петров Петр Сергеевич`
3. Lines with digits/symbols are ignored by design.

## Notes

- Keep files as UTF-8 text.
- One file represents one study group batch.
- Default import limits:
  - max `2 MB` per file
  - max `10 MB` total upload size
