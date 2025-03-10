document.addEventListener('alpine:init', () => {
    Alpine.data('scheduleForm', () => ({
        username: '',
        password: '',
        startDate: '',
        endDate: '',
        scheduleType: 'personal',
        filename: 'grafik.xlsx',
        message: '',
        minDate: '',
        maxDate: '',

        initializeDates() {
            const today = new Date();
            const year = today.getFullYear();

            this.minDate = `${year}-01-01`;
            this.maxDate = `${year}-12-31`;

            const currentDay = today.getDay();
            const monday = new Date(today);
            monday.setDate(today.getDate() - currentDay + 1);

            const currentWeekMonday = monday.toISOString().split('T')[0];

            this.startDate = currentWeekMonday;
            this.endDate = currentWeekMonday;
        },

        scrollToMessage() {
            // Wait for the DOM to update before scrolling
            this.$nextTick(() => {
                const messageElement = document.querySelector('.success-message');
                if (messageElement) {
                    const y = messageElement.getBoundingClientRect().top + window.pageYOffset;
                    window.scrollTo({top: y, behavior: 'smooth'});
                }
            });
        },

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
                a.download = this.filename;
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