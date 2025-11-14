// MainStream Shop - Main JavaScript

$(document).ready(function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Form validation
    initializeFormValidation();
    
    // Smooth scrolling for anchor links
    $('a[href*="#"]').not('[href="#"]').not('[href="#0"]').click(function(event) {
        if (location.pathname.replace(/^\//, '') == this.pathname.replace(/^\//, '') 
            && location.hostname == this.hostname) {
            var target = $(this.hash);
            target = target.length ? target : $('[name=' + this.hash.slice(1) + ']');
            if (target.length) {
                event.preventDefault();
                $('html, body').animate({
                    scrollTop: target.offset().top - 80
                }, 1000);
            }
        }
    });
});

// Form Validation
function initializeFormValidation() {
    // Phone number formatting
    $('input[type="tel"]').on('input', function() {
        let value = $(this).val().replace(/\D/g, '');
        if (value.length > 0) {
            if (value.length <= 1) {
                value = '+7';
            } else if (value.length <= 4) {
                value = '+7 (' + value.substring(1);
            } else if (value.length <= 7) {
                value = '+7 (' + value.substring(1, 4) + ') ' + value.substring(4);
            } else if (value.length <= 9) {
                value = '+7 (' + value.substring(1, 4) + ') ' + value.substring(4, 7) + '-' + value.substring(7);
            } else {
                value = '+7 (' + value.substring(1, 4) + ') ' + value.substring(4, 7) + '-' + value.substring(7, 9) + '-' + value.substring(9, 11);
            }
        }
        $(this).val(value);
    });
    
    // Email validation
    $('input[type="email"]').on('blur', function() {
        const email = $(this).val();
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        
        if (email && !emailRegex.test(email)) {
            $(this).addClass('is-invalid');
            if (!$(this).siblings('.invalid-feedback').length) {
                $(this).after('<div class="invalid-feedback">Введите корректный email адрес</div>');
            }
        } else {
            $(this).removeClass('is-invalid');
            $(this).siblings('.invalid-feedback').remove();
        }
    });
}

// Toast Notifications
function showToast(message, type = 'info') {
    const toastHtml = `
        <div class="toast align-items-center text-white bg-${type === 'error' ? 'danger' : type} border-0" role="alert">
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    
    // Create toast container if it doesn't exist
    if (!$('#toastContainer').length) {
        $('body').append('<div id="toastContainer" class="toast-container position-fixed top-0 end-0 p-3" style="z-index: 9999;"></div>');
    }
    
    // Add toast to container
    $('#toastContainer').append(toastHtml);
    
    // Show toast
    const toastElement = $('#toastContainer .toast:last');
    const toast = new bootstrap.Toast(toastElement[0]);
    toast.show();
    
    // Remove toast element after it's hidden
    toastElement.on('hidden.bs.toast', function() {
        $(this).remove();
    });
}

// Loading States
function showLoading(element) {
    const $element = $(element);
    $element.prop('disabled', true);
    $element.data('original-text', $element.text());
    $element.html('<span class="spinner-border spinner-border-sm me-2"></span>Загрузка...');
}

function hideLoading(element) {
    const $element = $(element);
    $element.prop('disabled', false);
    $element.text($element.data('original-text'));
}

// AJAX Form Submission
function submitForm(form, callback) {
    const $form = $(form);
    const $submitBtn = $form.find('button[type="submit"]');
    
    showLoading($submitBtn);
    
    $.ajax({
        url: $form.attr('action'),
        method: $form.attr('method') || 'POST',
        data: $form.serialize(),
        dataType: 'json',
        success: function(response) {
            hideLoading($submitBtn);
            if (response.success) {
                showToast(response.message || 'Операция выполнена успешно', 'success');
                if (callback) callback(response);
            } else {
                showToast(response.message || 'Произошла ошибка', 'error');
            }
        },
        error: function(xhr) {
            hideLoading($submitBtn);
            const response = xhr.responseJSON;
            showToast(response?.message || 'Произошла ошибка при выполнении запроса', 'error');
        }
    });
}

// Utility Functions
function formatCurrency(amount) {
    return new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: 'RUB',
        minimumFractionDigits: 0
    }).format(amount);
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
}

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

// Search functionality
function initializeSearch() {
    const searchInput = $('#searchInput');
    if (searchInput.length) {
        const debouncedSearch = debounce(function() {
            const query = $(this).val();
            if (query.length >= 2) {
                performSearch(query);
            }
        }, 300);
        
        searchInput.on('input', debouncedSearch);
    }
}

function performSearch(query) {
    // Implement search functionality
    console.log('Searching for:', query);
}

// Initialize search when document is ready
$(document).ready(function() {
    initializeSearch();
});
