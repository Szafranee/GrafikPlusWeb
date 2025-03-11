# GrafikPlusWeb

A web-based version of [GrafikPlus](https://github.com/Szafranee/GrafikPlus) - a tool for downloading and converting CanalPlus work schedules into Excel (.xlsx) files. This web application provides the same core functionality as the desktop version but with the convenience of web access.

🌐 **Available at: [grafikplus.xce.pl](https://grafikplus.xce.pl)**


## Features

- **Web-based Interface**: Access your schedules from any browser without installing software
- Download personal schedules and installation schedules as Excel (.xlsx) files
- Calendar-based week selection
- Remember last used username
- Customizable output file name and location
- Light/Dark theme (follows system settings)
- No installation required - just visit the website

## Quick Start

1. Go to [grafikplus.xce.pl](https://grafikplus.xce.pl)
2. Enter your CanalPlus credentials
3. Select schedule type (personal or installation)
4. Choose the date range
5. Click "Download Schedule"
6. Done! Your schedule will be downloaded as an Excel file

## System Requirements

- Any modern web browser
- Access to a CanalPlus employee account

## Troubleshooting

### Login Errors
- Verify your login credentials
- Check your internet connection
- Ensure you have access to CanalPlus systems

### File Download Issues
- Make sure your browser allows downloads
- Check if you have sufficient storage space
- Try using a different browser if issues persist

## Technical Details

### Frontend Technologies
- HTML5 & CSS3
- JavaScript with Alpine.js
- Responsive design for all devices

### Backend Technologies
- Python 3.x with Flask
- BeautifulSoup4 for parsing
- Requests for HTTP client
- Pandas for Excel export

### Project Structure
```
grafikplusweb/
├── app.py                 # Flask application entry point
├── backend/
│   ├── api/              # API endpoints
│   ├── config.py         # Configuration settings
│   ├── schedule_parser.py # Schedule parsing logic
│   └── schedule_scraper.py # Web scraping functionality
├── frontend/
│   ├── static/           # Static assets (CSS, JS, images)
│   └── templates/        # HTML templates
└── run.py               # Production server runner
```

## Related Projects

This is the web version of the original [GrafikPlus desktop application](https://github.com/Szafranee/GrafikPlus). If you prefer a standalone desktop application, check out the original project.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
