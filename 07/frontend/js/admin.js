// Dynamic API base — localhost for dev, real URL for Netlify/production
const ADMIN_API_BASE = (
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1'
) ? 'http://127.0.0.1:8000/api' : 'https://YOUR_BACKEND_URL_HERE/api';

async function loadDashboardData() {
    try {
        const token = localStorage.getItem('token');
        if (!token) return; // Prevent 401 errors during redirect
        
        const headers = { 'Authorization': `Bearer ${token}` };
        
        const [statsRes, usersRes] = await Promise.all([
            axios.get(`${ADMIN_API_BASE}/admin/dashboard-stats`, { headers }),
            axios.get(`${ADMIN_API_BASE}/admin/users`, { headers })
        ]);
        
        const stats = statsRes.data;
        const users = usersRes.data;
        
        document.getElementById('totalUsers').textContent = stats.total_users;
        document.getElementById('totalScans').textContent = stats.total_detections;
        document.getElementById('totalReports').textContent = stats.total_reports;
        
        // Chart.js Ratio Chart
        const ctx = document.getElementById('ratioChart').getContext('2d');
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Genuine', 'Fake'],
                datasets: [{
                    data: [stats.fake_ratio.genuine, stats.fake_ratio.fake],
                    backgroundColor: ['#10b981', '#ef4444'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { color: '#e2e8f0' }
                    }
                }
            }
        });
        
        // Populate Users Table
        const tbody = document.getElementById('usersTableBody');
        users.slice(0, 5).forEach(user => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-300">${user.name}</td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-300">${user.email}</td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-300">
                    <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${user.role === 'admin' ? 'bg-red-100 text-red-800' : 'bg-blue-100 text-blue-800'}">
                        ${user.role}
                    </span>
                </td>
            `;
            tbody.appendChild(tr);
        });
        
    } catch (error) {
        console.error('Failed to load dashboard data:', error);
    }
}
