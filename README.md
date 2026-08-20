# GrafikPlusWeb 
<a href="https://www.grafikplus.xce.pl/"><img alt="GrafikPlusWeb Banner" src="https://github.com/Szafranee/GrafikPlusWeb/blob/772b940e6a7712041a7b78b7c584f4c0427829ed/docs/images/GrafikPlus_banner.png" width="480"/></a>

> 🇵🇱 **GrafikPlusWeb** to narzędzie webowe do pobierania i konwertowania grafików pracy Canal+ do plików Excel (.xlsx). Aplikacja dostępna jest pod adresem [grafikplus.xce.pl](https://grafikplus.xce.pl)

A web-based version of [GrafikPlus](https://github.com/Szafranee/GrafikPlus) - a tool for downloading and converting CanalPlus work schedules into Excel (.xlsx) files. This web application provides the same core functionality as the desktop version but with the convenience of web access.

### 🌐 Available at: [grafikplus.xce.pl](https://grafikplus.xce.pl)

## 📋 Features

- **Web-based Interface**: Access your schedules from any browser without installing software
- Download personal schedules and installation schedules as Excel (.xlsx) files
- Calendar-based week selection
- Remember last used username
- Customizable output file name and location
- Light/Dark theme (follows system settings)
- No installation required - just visit the website
- **Program Title Mapping**:
  - Automatic mapping of program descriptions to standardized titles using CSV configuration
  - Live configuration updates - changes to mapping file are detected and applied automatically without restart
  - Efficient caching mechanism to optimize performance
- Template-based monthly reports that preserve the workbook's formulas, styles,
  validations, and embedded Excel extensions
- Password-protected administrator panel for replacing the XLSX template and CSV
  dictionary, and for configuring target cells

## 🚀 Quick Start

1. Go to [grafikplus.xce.pl](https://grafikplus.xce.pl)
2. Enter your Canal+ credentials
3. Select schedule type (personal or general)
4. Choose the start and end dates
5. Click "Pobierz grafik" (Download schedule)
6. Done! Your schedule will be downloaded as an Excel file 😎

## 💻 System Requirements

- Any modern web browser
- Access to a Canal+ employee account

## 🔧 Troubleshooting

### Login Errors
- Verify your login credentials
- Check your internet connection
- Ensure you have access to Canal+ systems

### File Download Issues
- Make sure your browser allows downloads
- Check if you have sufficient storage space
- Try using a different browser if issues persist

## 🛠️ Tech Stack

### Frontend
- HTML5 & CSS3
- JavaScript with Alpine.js
- Responsive design for all devices

### Backend
- Python 3.x with Flask
- BeautifulSoup4 for parsing
- Requests for HTTP client
- OpenPyXL for Excel export

## 🧪 Development

### Prerequisites
- Python 3.12 (the version used by the production Passenger application)
- Git
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### Local Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/GrafikPlusWeb.git
cd GrafikPlusWeb

# Create the local environment and install the locked dependencies
uv sync

# Run development server
uv run python run.py
```

Run the deterministic unit and integration tests with:

```bash
uv run python -m unittest discover -v
```

The suite uses local HTML fixtures and mocked HTTP responses, so it does not
normally contact the external schedule service. To additionally verify the
current login endpoint, schedule URL, live HTML structure, parser, and XLSX
export, configure the `LIVE_SCHEDULE_*` values shown in `.env.example`, choose a
date known to contain entries, and explicitly set
`RUN_LIVE_SCHEDULE_TESTS=true`. Never enable the live test in public CI.

Copy `.env.example` to `.env` and set `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and a
random `SECRET_KEY` before opening `/admin/`. The browser displays its native
HTTP Basic Auth dialog. If the administrator credentials are missing, the panel
is disabled and returns HTTP 503.

The template exporter is active by default. Set `USE_TEMPLATE_EXPORT=false` to
restore the legacy standalone workbook exporter without removing it from the
application. The bundled `report_template.xlsx` is used until an administrator
uploads a replacement; uploaded templates and saved mappings are kept in the
ignored `instance/` directory.

### 📦 Dependency Management

Use `uv` for all dependency changes so that `pyproject.toml` and `uv.lock` stay in sync:

```bash
# Add a runtime dependency
uv add package-name

# Upgrade and install all dependencies
uv lock --upgrade && uv sync
```

## 🚢 Deployment

The project includes PowerShell and Bash deployment scripts with presets, changed-file detection, remote dependency synchronization, and Phusion Passenger restarts. See [DEPLOYMENT.md](DEPLOYMENT.md) for setup and usage.

## 🔍 Project Structure
```
grafikplusweb/
├── app.py                 # Flask application entry point
├── pyproject.toml         # Project metadata and dependencies
├── uv.lock                # Reproducible dependency lock file
├── .python-version        # Python version used by uv
├── backend/
│   ├── api/              # API endpoints
│   ├── config.py         # Configuration settings
│   ├── schedule_parser.py # Schedule parsing logic
│   ├── schedule_scraper.py # Web scraping functionality
│   └── data/
│       └── program_titles.csv # Program titles mapping (auto-refreshed)
├── frontend/
│   ├── static/           # Static assets (CSS, JS, images)
│   └── templates/        # HTML templates
└── run.py                # Production server runner
```

## 🔒 Security

- Credentials are not stored on the server
- HTTPS encryption
- Session-based authentication

## 📚 Related Projects

This is the web version of the original [GrafikPlus desktop application](https://github.com/Szafranee/GrafikPlus). If you prefer a standalone desktop application, check out the original project.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
