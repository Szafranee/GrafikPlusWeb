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
  - Fallback to original descriptions if mapping is not found

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
- Pandas for Excel export

## 🧪 Development

### Prerequisites
- Python 3.x
- Git

### Local Setup
```bash
# Clone the repository
git clone https://github.com/yourusername/GrafikPlusWeb.git

# Install dependencies
pip install -r requirements.txt

# Run development server
python app.py
```

## 🔍 Project Structure
```
grafikplusweb/
├── app.py                 # Flask application entry point
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
