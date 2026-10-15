function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    const icon = document.getElementById('themeIcon');
    const label = document.getElementById('themeLabel');
    const emoji = document.getElementById('themeEmoji');
    if(icon) icon.textContent = theme === 'dark' ? '☀️' : '🌙';
    if(label) label.textContent = theme === 'dark' ? 'Dark' : 'Light';
    if(emoji) emoji.textContent = theme === 'dark' ? '🌙' : '☀️';
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = current === 'dark' ? 'light' : 'dark';
    applyTheme(newTheme);
}

// Run immediately on script execution to prevent flash
(function() {
    const saved = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
})();

document.addEventListener('DOMContentLoaded', () => {
    // Apply saved theme state and update UI labels
    const saved = localStorage.getItem('theme') || 'dark';
    applyTheme(saved);

    // 1. Inject Background Animated Orbs
    if (!document.querySelector('.bg-orbs')) {
        const orbsContainer = document.createElement('div');
        orbsContainer.className = 'bg-orbs';
        orbsContainer.innerHTML = `
            <div class="orb orb-1"></div>
            <div class="orb orb-2"></div>
            <div class="orb orb-3"></div>
        `;
        document.body.prepend(orbsContainer);
    }

    // 2. Custom Intersection Observer for Animations
    const observerOptions = {
        root: null,
        rootMargin: '0px',
        threshold: 0.15
    };

    const observer = new IntersectionObserver((entries, obs) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate-in');
                obs.unobserve(entry.target); 
            }
        });
    }, observerOptions);

    document.querySelectorAll('.animate').forEach(el => {
        observer.observe(el);
    });

    // 3. Global Theme Toggle Injection
    const navActions = document.querySelector('.nav-actions') || 
                       document.querySelector('.user-nav-right') || 
                       document.querySelector('.admin-nav-right');
    
    if (navActions && !document.getElementById('themeToggle')) {
        const themeBtn = document.createElement('button');
        themeBtn.id = 'themeToggle';
        themeBtn.type = 'button';
        themeBtn.title = 'Toggle Light/Dark Theme';
        themeBtn.innerHTML = '<span id="themeIcon">☀️</span>';
        navActions.insertBefore(themeBtn, navActions.firstChild);
    }
    
    const themeBtn = document.getElementById('themeToggle');
    if (themeBtn) {
        themeBtn.onclick = toggleTheme;
    }
    
    applyTheme(saved);
});
