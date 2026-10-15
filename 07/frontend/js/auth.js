// Dynamic API base — localhost for dev, real URL for Netlify/production
const API_BASE_URL = (
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1'
) ? 'http://127.0.0.1:8000/api' : 'https://YOUR_BACKEND_URL_HERE/api';



document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');

    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;

            try {
                const response = await axios.post(`${API_BASE_URL}/auth/login`, {
                    email,
                    password
                });
                
                const data = response.data;
                localStorage.setItem('token', data.access_token);
                localStorage.setItem('role', data.role);
                localStorage.setItem('user_name', data.name);
                localStorage.setItem('userName', data.name);
                localStorage.setItem('userEmail', data.email || '');
                localStorage.setItem('userRole', data.role);
                
                Swal.fire({
                    icon: 'success',
                    title: 'Welcome back!',
                    text: 'Login successful.',
                    background: '#1e293b',
                    color: '#fff',
                    showConfirmButton: false,
                    timer: 1500
                }).then(() => {
                    if (data.role === 'admin') {
                        window.location.href = 'admin/dashboard.html';
                    } else {
                        window.location.href = 'dashboard.html';
                    }
                });
            } catch (error) {
                Swal.fire({
                    icon: 'error',
                    title: 'Login Failed',
                    text: error.response?.data?.detail || 'Something went wrong',
                    background: '#1e293b',
                    color: '#fff'
                });
            }
        });
    }

    if (registerForm) {
        registerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = document.getElementById('name').value;
            const email = document.getElementById('email').value;
            const phone = document.getElementById('phone')?.value || null;
            const password = document.getElementById('password').value;

            try {
                await axios.post(`${API_BASE_URL}/auth/register`, {
                    name, email, phone, password
                });
                
                Swal.fire({
                    icon: 'success',
                    title: 'Account Created!',
                    text: 'You can now login.',
                    background: '#1e293b',
                    color: '#fff',
                    showConfirmButton: false,
                    timer: 1500
                }).then(() => {
                    window.location.href = 'login.html';
                });
            } catch (error) {
                Swal.fire({
                    icon: 'error',
                    title: 'Registration Failed',
                    text: error.response?.data?.detail || 'Something went wrong',
                    background: '#1e293b',
                    color: '#fff'
                });
            }
        });
    }

    // Forgot Password & OTP Flow
    const forgotPasswordLink = document.getElementById('forgotPasswordLink');
    const backToLoginLink = document.getElementById('backToLoginLink');
    const loginSection = document.getElementById('loginSection');
    const forgotPasswordSection = document.getElementById('forgotPasswordSection');
    const resetPasswordSection = document.getElementById('resetPasswordSection');
    const forgotForm = document.getElementById('forgotForm');
    const resetForm = document.getElementById('resetForm');
    const resendOtpLink = document.getElementById('resendOtpLink');

    let resetEmail = '';

    if (forgotPasswordLink) {
        forgotPasswordLink.addEventListener('click', (e) => {
            e.preventDefault();
            loginSection.style.display = 'none';
            forgotPasswordSection.style.display = 'block';
            resetPasswordSection.style.display = 'none';
            document.getElementById('forgotEmail').focus();
        });
    }

    if (backToLoginLink) {
        backToLoginLink.addEventListener('click', (e) => {
            e.preventDefault();
            forgotPasswordSection.style.display = 'none';
            resetPasswordSection.style.display = 'none';
            loginSection.style.display = 'block';
        });
    }

    if (forgotForm) {
        forgotForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('forgotEmail').value;
            resetEmail = email;

            try {
                Swal.fire({
                    title: 'Sending OTP...',
                    html: 'Please wait while we verify your request.',
                    allowOutsideClick: false,
                    didOpen: () => {
                        Swal.showLoading();
                    },
                    background: '#1e293b',
                    color: '#fff'
                });
                
                const response = await axios.post(`${API_BASE_URL}/auth/forgot-password`, { email });
                
                Swal.fire({
                    icon: 'success',
                    title: 'OTP Code Sent!',
                    text: response.data.message || 'Please check your email/console for the 6-digit OTP code.',
                    background: '#1e293b',
                    color: '#fff',
                    confirmButtonColor: '#6C63FF'
                }).then(() => {
                    forgotPasswordSection.style.display = 'none';
                    resetPasswordSection.style.display = 'block';
                    document.getElementById('resetOtp').focus();
                });
            } catch (error) {
                Swal.fire({
                    icon: 'error',
                    title: 'Request Failed',
                    text: error.response?.data?.detail || 'Could not initiate password reset request. Please check email address.',
                    background: '#1e293b',
                    color: '#fff'
                });
            }
        });
    }

    if (resetForm) {
        resetForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const otp_code = document.getElementById('resetOtp').value;
            const new_password = document.getElementById('newPassword').value;
            const confirm_password = document.getElementById('confirmPassword').value;

            if (new_password !== confirm_password) {
                Swal.fire({
                    icon: 'warning',
                    title: 'Password Mismatch',
                    text: 'New password and confirm password fields must match.',
                    background: '#1e293b',
                    color: '#fff'
                });
                return;
            }

            try {
                Swal.fire({
                    title: 'Resetting Password...',
                    html: 'Updating database credentials.',
                    allowOutsideClick: false,
                    didOpen: () => {
                        Swal.showLoading();
                    },
                    background: '#1e293b',
                    color: '#fff'
                });
                
                const response = await axios.post(`${API_BASE_URL}/auth/reset-password`, {
                    email: resetEmail,
                    otp_code,
                    new_password
                });

                Swal.fire({
                    icon: 'success',
                    title: 'Password Reset Successful!',
                    text: response.data.message || 'You can now login with your new password.',
                    background: '#1e293b',
                    color: '#fff',
                    confirmButtonColor: '#6C63FF'
                }).then(() => {
                    resetPasswordSection.style.display = 'none';
                    forgotPasswordSection.style.display = 'none';
                    loginSection.style.display = 'block';
                    // clear forms
                    forgotForm.reset();
                    resetForm.reset();
                });
            } catch (error) {
                Swal.fire({
                    icon: 'error',
                    title: 'Reset Failed',
                    text: error.response?.data?.detail || 'Invalid or expired OTP code. Please try again.',
                    background: '#1e293b',
                    color: '#fff'
                });
            }
        });
    }

    if (resendOtpLink) {
        resendOtpLink.addEventListener('click', async (e) => {
            e.preventDefault();
            if (!resetEmail) {
                Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: 'Session expired. Please start forgot password process again.',
                    background: '#1e293b',
                    color: '#fff'
                });
                return;
            }

            try {
                Swal.fire({
                    title: 'Resending OTP...',
                    html: 'Please wait...',
                    allowOutsideClick: false,
                    didOpen: () => {
                        Swal.showLoading();
                    },
                    background: '#1e293b',
                    color: '#fff'
                });
                
                const response = await axios.post(`${API_BASE_URL}/auth/forgot-password`, { email: resetEmail });
                
                Swal.fire({
                    icon: 'success',
                    title: 'OTP Resent!',
                    text: response.data.message || 'A new OTP code has been dispatched.',
                    background: '#1e293b',
                    color: '#fff',
                    confirmButtonColor: '#6C63FF'
                });
            } catch (error) {
                Swal.fire({
                    icon: 'error',
                    title: 'Resend Failed',
                    text: error.response?.data?.detail || 'Could not resend OTP. Please try again later.',
                    background: '#1e293b',
                    color: '#fff'
                });
            }
        });
    }
});

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    localStorage.removeItem('user_name');
    // Detect if we're inside admin/ subfolder
    const isAdmin = window.location.pathname.includes('/admin/');
    window.location.href = isAdmin ? '../login.html' : 'login.html';
}

function checkAuth(roleRequired = null) {
    const token = localStorage.getItem('token');
    const role = localStorage.getItem('role');
    const isAdmin = window.location.pathname.includes('/admin/');
    
    if (!token) {
        window.location.href = isAdmin ? '../login.html' : 'login.html';
        return;
    }
    
    if (roleRequired && role !== roleRequired) {
        if (role === 'admin') {
            window.location.href = isAdmin ? 'dashboard.html' : 'admin/dashboard.html';
        } else {
            window.location.href = isAdmin ? '../dashboard.html' : 'dashboard.html';
        }
        return;
    }

    // Populate sidebar info after DOM loads
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', populateSidebar);
    } else {
        populateSidebar();
    }
}

function populateSidebar() {
    const token = localStorage.getItem('token');
    const userName = localStorage.getItem('user_name') || 'User';
    
    document.querySelectorAll('.auth-name').forEach(el => el.textContent = userName);
    document.querySelectorAll('.auth-avatar').forEach(el => el.textContent = userName.charAt(0).toUpperCase());
    
    const userNameElem = document.getElementById('userNameDisplay');
    if (userNameElem) userNameElem.textContent = userName;
    const userAvatarElem = document.getElementById('userAvatar');
    if (userAvatarElem) userAvatarElem.textContent = userName.charAt(0).toUpperCase();
    
    if (token) {
        try {
            const base64Url = token.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(window.atob(base64).split('').map(function(c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
            const payload = JSON.parse(jsonPayload);
            
            document.querySelectorAll('.auth-email').forEach(el => el.textContent = payload.sub);
            
            const userEmailElem = document.getElementById('userEmailDisplay');
            if (userEmailElem && payload.sub) {
                userEmailElem.textContent = payload.sub;
            }
        } catch (e) {
            console.error('Failed to parse user email from token:', e);
        }
    }
}
