/**
 * JavaScript for Facial Recognition Attendance System
 * Handles UI interactions and API calls
 */

// Show modern toast notification
const showToast = (message, type = 'info') => {
    const box = document.getElementById('messageBox');
    const textNode = document.getElementById('messageText');
    const iconNode = document.getElementById('messageIcon');
    
    if(!box || !textNode) return;

    textNode.textContent = message;
    
    // Clear old classes
    box.classList.remove('success', 'error', 'info', 'show');
    iconNode.className = '';
    
    // Set type and icon
    box.classList.add(type);
    if(type === 'success') {
        iconNode.className = 'ph-fill ph-check-circle';
    } else if(type === 'error') {
        iconNode.className = 'ph-fill ph-warning-circle';
    } else {
        iconNode.className = 'ph-fill ph-info';
    }
    
    // Show
    box.classList.add('show');
    
    setTimeout(() => {
        box.classList.remove('show');
    }, 4000);
};

// Aliased for backwards compatibility in forms if needed
const showMessage = showToast;

// Format date to YYYY-MM-DD
function formatDate(date) {
    const d = new Date(date);
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// Format time to HH:MM:SS
function formatTime(time) {
    if (typeof time === 'string' && time.includes(':')) {
        return time;
    }
    const t = new Date(time);
    const hours = String(t.getHours()).padStart(2, '0');
    const minutes = String(t.getMinutes()).padStart(2, '0');
    const seconds = String(t.getSeconds()).padStart(2, '0');
    return `${hours}:${minutes}:${seconds}`;
}

// Validate form inputs
function validateForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return false;
    
    const inputs = form.querySelectorAll('input[required]');
    let isValid = true;
    
    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.style.borderColor = '#f56565';
            isValid = false;
        } else {
            input.style.borderColor = '#e2e8f0';
        }
    });
    
    return isValid;
}

// Check if XAMPP is running
async function checkXAMPPStatus() {
    try {
        const response = await fetch('/api/get_users');
        if (!response.ok) {
            showMessage('⚠️ Cannot connect to database. Make sure XAMPP MySQL is running!', 'error');
            return false;
        }
        return true;
    } catch (error) {
        showMessage('⚠️ Cannot connect to database. Make sure XAMPP MySQL is running!', 'error');
        return false;
    }
}

// Debounce function to prevent multiple rapid calls
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Confirm action dialog
function confirmAction(message) {
    return confirm(message);
}

// Copy text to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showMessage('Copied to clipboard!', 'success');
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

// Download data as JSON
function downloadJSON(data, filename) {
    const dataStr = JSON.stringify(data, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
}

// Initialize tooltips (if needed)
function initializeTooltips() {
    const tooltips = document.querySelectorAll('[data-tooltip]');
    tooltips.forEach(element => {
        element.addEventListener('mouseenter', (e) => {
            const tooltip = document.createElement('div');
            tooltip.className = 'tooltip';
            tooltip.textContent = e.target.getAttribute('data-tooltip');
            document.body.appendChild(tooltip);
            
            const rect = e.target.getBoundingClientRect();
            tooltip.style.top = `${rect.top - 40}px`;
            tooltip.style.left = `${rect.left}px`;
        });
        
        element.addEventListener('mouseleave', () => {
            const tooltip = document.querySelector('.tooltip');
            if (tooltip) {
                tooltip.remove();
            }
        });
    });
}

// Handle API errors
function handleAPIError(error, customMessage = 'An error occurred') {
    console.error('API Error:', error);
    showMessage(`${customMessage}: ${error.message}`, 'error');
}

// Loading indicator
function showLoading(show = true) {
    let loader = document.getElementById('loadingIndicator');
    
    if (!loader) {
        loader = document.createElement('div');
        loader.id = 'loadingIndicator';
        loader.innerHTML = '<div class="spinner"></div><p>Loading...</p>';
        loader.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 30px;
            border-radius: 10px;
            z-index: 9999;
            text-align: center;
        `;
        document.body.appendChild(loader);
    }
    
    loader.style.display = show ? 'block' : 'none';
}

// Check browser compatibility
function checkBrowserCompatibility() {
    const isCompatible = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    
    if (!isCompatible) {
        showMessage('⚠️ Your browser does not support webcam access. Please use Chrome, Firefox, or Edge.', 'error');
        return false;
    }
    
    return true;
}

// Request webcam permission
async function requestWebcamPermission() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        stream.getTracks().forEach(track => track.stop()); // Stop the stream immediately
        return true;
    } catch (error) {
        showMessage('⚠️ Webcam access denied. Please allow camera access in your browser settings.', 'error');
        return false;
    }
}

// Initialize page
document.addEventListener('DOMContentLoaded', () => {
    // Check browser compatibility
    checkBrowserCompatibility();
    
    // Check XAMPP status
    checkXAMPPStatus();
    
    // Initialize tooltips if any
    initializeTooltips();
    
    console.log('📱 Facial Recognition Attendance System Initialized');
});

// Handle page visibility change (pause video when tab is hidden)
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        console.log('Page hidden - consider pausing video stream');
    } else {
        console.log('Page visible - resume video stream');
    }
});

// Utility: Get current timestamp
function getCurrentTimestamp() {
    return new Date().toISOString();
}

// Utility: Format large numbers with commas
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Export functions to global scope
window.showToast = showToast;
window.showMessage = showMessage;
window.formatDate = formatDate;
window.formatTime = formatTime;
window.validateForm = validateForm;
window.checkXAMPPStatus = checkXAMPPStatus;
window.confirmAction = confirmAction;
window.copyToClipboard = copyToClipboard;
window.downloadJSON = downloadJSON;
window.showLoading = showLoading;
window.requestWebcamPermission = requestWebcamPermission;