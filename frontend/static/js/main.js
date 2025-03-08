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
         * Generates the weeks array and sets initial values
         * Called on component initialization
         */
        generateWeeks() {
            const today = new Date();
            const year = today.getFullYear();
            const weeks = [];

            // Calculate current week number
            const currentWeek = Math.ceil(
                (today - new Date(year, 0, 1)) / (7 * 24 * 60 * 60 * 1000)
            );

            // Generate array of weeks for the entire year
            for (let i = 1; i <= 52; i++) {
                // Calculate start and end dates for each week
                let startDate = new Date(year, 0, (i - 1) * 7 + 1);
                let endDate = new Date(startDate);
                endDate.setDate(startDate.getDate() + 6);

                // Create week object with value and label
                let label = `Tydzień ${i} (${startDate.toLocaleDateString('pl-PL')} - ${endDate.toLocaleDateString('pl-PL')})`;
                weeks.push({value: `week-${i}`, label});
            }

            // Update component state
            this.weeks = weeks;
            this.startWeek = `week-${currentWeek}`;
            this.endWeek = `week-${currentWeek}`;

            // Force update of select elements after render
            this.$nextTick(() => {
                document.getElementById('startWeek').value = `week-${currentWeek}`;
                document.getElementById('endWeek').value = `week-${currentWeek}`;
            });
        },

        /**
         * Handles form submission and API communication
         * @returns {Promise<void>}
         */
        async submitForm() {
            try {
                // Convert week number to date
                const getDateFromWeek = (weekStr) => {
                    const weekNum = parseInt(weekStr.replace('week-', ''));
                    const year = new Date().getFullYear();
                    const firstDayOfYear = new Date(year, 0, 1);
                    const date = new Date(firstDayOfYear);
                    date.setDate(firstDayOfYear.getDate() + (weekNum - 1) * 7);
                    return date.toISOString().split('T')[0]; // Format YYYY-MM-DD
                };

                // Prepare data for API
                const formData = {
                    username: this.username,
                    password: this.password,
                    startDate: getDateFromWeek(this.startWeek),
                    endDate: getDateFromWeek(this.endWeek),
                    isPersonal: this.scheduleType === 'personal'
                };

                this.message = '⏳ Pobieranie grafiku...';

                // Call API
                const response = await fetch('http://localhost:5000/api/schedule', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(formData)
                });

                // Check if response is OK
                if (!response.ok) {
                    const errorData = await response.json();
                    console.log('Error response:', errorData);
                    if (errorData.title && errorData.message) {
                        this.message = `❌ ${errorData.title}: ${errorData.message}`;
                    }
                    throw new Error(`Error: ${response.status} ${response.statusText}`);
                }

                // Get file
                const blob = await response.blob();

                // Create download link
                const downloadUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = this.filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(downloadUrl);

                this.message = '✅ Grafik został pobrany!';

                // Clear success message after 3 seconds
                setTimeout(() => {
                    this.message = '';
                }, 3000);

            } catch (error) {
                console.error('Error:', error);

                // // Clear error message after 5 seconds
                // setTimeout(() => {
                //     this.message = '';
                // }, 5000);
            }
        }
    }))

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