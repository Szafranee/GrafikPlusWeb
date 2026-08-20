document.addEventListener('alpine:init', () => {
    Alpine.data('scheduleForm', () => ({
        username: localStorage.getItem('lastUsername') || '',
        password: '',
        startDate: '',
        endDate: '',
        scheduleType: 'personal',
        filename: 'grafik.xlsx',
        templateExportEnabled: true,
        filenameLocked: true,
        reportActivity: 'MONTAŻ',
        reportMonth: '',
        reportYear: '',
        message: '',
        minDate: '',
        maxDate: '',

        initializeDates() {
            const today = new Date();
            const currentYear = today.getFullYear();

            // Set date range to previous year and next year
            this.minDate = `${currentYear - 1}-01-01`;
            this.maxDate = `${currentYear + 1}-12-31`;

            // Set current week as default selection
            const currentDay = today.getDay();
            const monday = new Date(today);
            monday.setDate(today.getDate() - currentDay + 1);

            const currentWeekMonday = monday.toISOString().split('T')[0];

            this.startDate = currentWeekMonday;
            this.endDate = currentWeekMonday;
            const polishMonths = [
                'STYCZEŃ', 'LUTY', 'MARZEC', 'KWIECIEŃ', 'MAJ', 'CZERWIEC',
                'LIPIEC', 'SIERPIEŃ', 'WRZESIEŃ', 'PAŹDZIERNIK', 'LISTOPAD', 'GRUDZIEŃ'
            ];
            this.reportMonth = polishMonths[today.getMonth()];
            this.reportYear = today.getFullYear();
            this.updateFilenamePreview();
            this.loadExportMode();
        },

        async loadExportMode() {
            try {
                const response = await fetch('/api/export-config');
                if (response.ok) {
                    const config = await response.json();
                    this.templateExportEnabled = config.templateExportEnabled;
                    this.reportActivity = config.activityValue;
                    this.reportMonth = config.month;
                    this.reportYear = config.year;
                    this.filenameLocked = config.templateExportEnabled;
                    if (this.filenameLocked) {
                        this.updateFilenamePreview();
                    } else {
                        this.filename = 'grafik.xlsx';
                    }
                }
            } catch (error) {
                console.warn('Could not load export mode:', error);
            }
        },

        filenameComponent(value, fallback) {
            const normalized = (value || '')
                .normalize('NFC')
                .replace(/[^\p{L}\p{N}_-]+/gu, '_')
                .replace(/^_+|_+$/g, '');
            return normalized || fallback;
        },

        updateFilenamePreview() {
            if (!this.templateExportEnabled || !this.filenameLocked) {
                return;
            }
            const loginParts = this.username
                .trim()
                .split('.')
                .map(part => part.trim())
                .filter(Boolean);
            const firstName = this.filenameComponent(loginParts[0], 'IMIĘ');
            const lastName = this.filenameComponent(
                loginParts.slice(1).join('_'),
                'NAZWISKO'
            );
            const activity = this.filenameComponent(this.reportActivity, 'CZYNNOŚĆ');
            const month = this.filenameComponent(this.reportMonth, 'MIESIĄC');
            this.filename = `${lastName}_${firstName}_${activity}_RAPORT_${month}_${this.reportYear || 'ROK'}.XLSX`
                .toLocaleUpperCase('pl-PL');
        },

        toggleFilenameLock() {
            this.filenameLocked = !this.filenameLocked;
            if (this.filenameLocked) {
                this.updateFilenamePreview();
            }
        },

        normalizedDownloadFilename(filename) {
            const safeName = (filename || 'grafik.xlsx')
                .trim()
                .replace(/[\\/:*?"<>|]+/g, '_');
            return safeName.toLowerCase().endsWith('.xlsx')
                ? safeName
                : `${safeName}.xlsx`;
        },

        scrollToMessage() {
            // Wait for the DOM to update and message to be visible
            setTimeout(() => {
                const messageElement = document.querySelector('.success-message');
                if (messageElement) {
                    // Calculate the element's position relative to the viewport
                    const elementRect = messageElement.getBoundingClientRect();
                    const absoluteElementTop = elementRect.top + window.pageYOffset;
                    const middle = absoluteElementTop - (window.innerHeight / 2) + (elementRect.height / 2);
                    
                    // Smooth scroll to the element
                    window.scrollTo({
                        top: middle,
                        behavior: 'smooth'
                    });
                }
            }, 100); // Small delay to ensure the message is rendered
        },

        getDownloadFilename(response) {
            const disposition = response.headers.get('Content-Disposition') || '';
            const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
            if (encoded) {
                try {
                    return decodeURIComponent(encoded[1]);
                } catch (_) {
                    // Fall back to the plain filename below.
                }
            }
            const plain = disposition.match(/filename="?([^";]+)"?/i);
            return plain ? plain[1] : 'grafik.xlsx';
        },

        async submitForm() {
            try {
                // Save username to localStorage
                localStorage.setItem('lastUsername', this.username);
                
                const formData = {
                    username: this.username,
                    password: this.password,
                    startDate: this.startDate,
                    endDate: this.endDate,
                    isPersonal: this.scheduleType === 'personal'
                };

                this.message = '⏳ Pobieranie grafiku...';
                this.scrollToMessage();

                const response = await fetch('/api/schedule', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(formData)
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.message || 'Wystąpił błąd');
                }

                const blob = await response.blob();
                const downloadUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = this.filenameLocked
                    ? this.getDownloadFilename(response)
                    : this.normalizedDownloadFilename(this.filename);
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(downloadUrl);

                this.message = '✅ Grafik został pobrany!';
                this.scrollToMessage();

                setTimeout(() => {
                    this.message = '';
                }, 4000);

            } catch (error) {
                console.error('Error:', error);
                this.message = `❌ ${error.message}`;
                this.scrollToMessage();

                setTimeout(() => {
                    this.message = '';
                }, 5000);
            }
        }
    }));

    Alpine.data('themeHandler', () => ({
        theme: localStorage.getItem('theme') ||
            (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),

        toggleTheme() {
            this.theme = this.theme === 'light' ? 'dark' : 'light';
            localStorage.setItem('theme', this.theme);
        }
    }));
});
