// Initialize Alpine.js components when the framework is ready
document.addEventListener('alpine:init', () => {
    // Main form handling component
    Alpine.data('scheduleForm', () => ({
        // Form state variables
        username: '',
        password: '',
        startWeek: '',
        endWeek: '',
        scheduleType: 'personal',  // Default to personal schedule
        filename: 'grafik.xlsx',   // Default filename
        message: '',               // Status message
        weeks: [],                 // Available weeks array

        /**
         * Initialize date inputs with current week
         */
        initializeDates() {
            const today = new Date();
            const year = today.getFullYear();

            // Set min date to start of current year
            this.minDate = `${year}-01-01`;

            // Set max date to end of current year
            this.maxDate = `${year}-12-31`;

            // Set default dates to current week
            const currentDay = today.getDay();
            const monday = new Date(today);
            monday.setDate(today.getDate() - currentDay + 1);

            const sunday = new Date(monday);
            sunday.setDate(monday.getDate() + 6);

            this.startDate = monday.toISOString().split('T')[0];
            this.endDate = sunday.toISOString().split('T')[0];
        },

        /**
         * Handle form submission
         */
        async submitForm() {
            try {
                const formData = {
                    username: this.username,
                    password: this.password,
                    startDate: this.startDate,
                    endDate: this.endDate,
                    isPersonal: this.scheduleType === 'personal'
                };

                this.message = '⏳ Pobieranie grafiku...';

                const response = await fetch('http://localhost:5000/api/schedule', {
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
                a.download = this.filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(downloadUrl);

                this.message = '✅ Grafik został pobrany!';
                setTimeout(() => this.message = '', 3000);

            } catch (error) {
                console.error('Error:', error);
                this.message = `❌ ${error.message}`;
                setTimeout(() => this.message = '', 5000);
            }
        }
    }));

    // Theme handling component
    Alpine.data('themeHandler', () => ({
        // Get theme from localStorage or system preferences
        theme: localStorage.getItem('theme') ||
            (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),

        /**
         * Toggles between light and dark theme
         * Persists selection to localStorage
         */
        toggleTheme() {
            this.theme = this.theme === 'light' ? 'dark' : 'light';
            localStorage.setItem('theme', this.theme);
        }
    }));
});