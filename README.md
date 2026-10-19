# Founder's Weekly Brief

The report keeps its layout in `templates/weekly_brief.html`. Edit `weekly_data.json` to update a week's content and figures; `generate_report.py` validates the input, formats KPI values, builds chart geometry, and renders `index.html`.

## Generate

Install the single dependency, then render the sample data:

```sh
python3 -m pip install -r requirements.txt
python3 generate_report.py
```

Use another data or output file with `--data path/to/data.json` and `--output path/to/report.html`.

All report content is escaped by Jinja2. Required fields and supported KPI formats are checked before rendering. Previous KPI values, chart series, status counts, disclaimers, footer notes, and recommendations can be omitted; unavailable metrics display a clear message or an empty chart state rather than a fabricated number. The three KPI slots and their order are part of the fixed layout.

Run the focused checks with `python3 -m unittest`.