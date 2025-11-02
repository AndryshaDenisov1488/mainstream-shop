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

    // Cart functionality
    initializeCart();
    
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

// Cart Management
function initializeCart() {
    // Load cart from localStorage
    loadCart();
    
    // Update cart display
    updateCartDisplay();
    
    // Bind cart events
    $(document).on('click', '.add-to-cart', function(e) {
        e.preventDefault();
        const button = $(this);
        const athleteId = button.data('athlete-id');
        const athleteName = button.data('athlete-name');
        const eventId = button.data('event-id');
        const eventName = button.data('event-name');
        const categoryId = button.data('category-id');
        const categoryName = button.data('category-name');
        
        // Show video type selection modal
        showVideoTypeModal(athleteId, athleteName, eventId, eventName, categoryId, categoryName);
    });
    
    
    $(document).on('click', '.clear-cart', function(e) {
        e.preventDefault();
        clearCart();
    });
}

function loadCart() {
    const cartData = localStorage.getItem('mainstream_cart');
    if (cartData) {
        window.cart = JSON.parse(cartData);
    } else {
        window.cart = [];
    }
}

function saveCart() {
    localStorage.setItem('mainstream_cart', JSON.stringify(window.cart));
}

function updateCartDisplay() {
    const count = window.cart.length;
    $('#cartCount').text(count);
    
    if (count > 0) {
        $('#cartBtn').removeClass('btn-outline-primary').addClass('btn-primary');
    } else {
        $('#cartBtn').removeClass('btn-primary').addClass('btn-outline-primary');
    }
}

function addToCart(item) {
    window.cart.push(item);
    saveCart();
    updateCartDisplay();
    showToast('Товар добавлен в корзину', 'success');
}


function clearCart() {
    window.cart = [];
    saveCart();
    updateCartDisplay();
    showToast('Корзина очищена', 'info');
}

function getCartTotal() {
    return window.cart.reduce((total, item) => total + (item.price * item.quantity), 0);
}

// Video Type Selection Modal
function showVideoTypeModal(athleteId, athleteName, eventId, eventName, categoryId, categoryName) {
    // Get video types from server
    $.get('/api/video-types')
        .done(function(videoTypes) {
            createVideoTypeModal(athleteId, athleteName, eventId, eventName, categoryId, categoryName, videoTypes);
        })
        .fail(function() {
            // Fallback to mock data if API fails
            const videoTypes = [
                { id: 1, name: 'Спорт версия 1', price: 999, description: 'Обычное видео одного проката, записанное на флешку. FullHD 1920/1080 50p.' },
                { id: 2, name: 'ТВ версия 1', price: 1499, description: 'ТВ-видео одного проката: профессиональная графика, замедленные повторы. FullHD 1920/1080 50p.' },
                { id: 3, name: 'Спорт версия 2', price: 1499, description: 'Два видео прокатов (КП + ПП), записанные на флешку. FullHD 1920/1080 50p.' },
                { id: 4, name: 'ТВ версия 2', price: 2499, description: 'ТВ-видео двух прокатов (КП + ПП): профессиональная графика, повторы. FullHD 1920/1080 50p.' }
            ];
            createVideoTypeModal(athleteId, athleteName, eventId, eventName, categoryId, categoryName, videoTypes);
        });
}

function createVideoTypeModal(athleteId, athleteName, eventId, eventName, categoryId, categoryName, videoTypes) {
    
    let modalHtml = `
        <div class="modal fade" id="videoTypeModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Выберите тип видео</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="mb-3">
                            <h6>Спортсмен: ${athleteName}</h6>
                            <small class="text-muted">${eventName} - ${categoryName}</small>
                        </div>
                        <div class="row">
    `;
    
    videoTypes.forEach(type => {
        modalHtml += `
            <div class="col-md-6 mb-3">
                <div class="video-type-card" data-type-id="${type.id}" data-price="${type.price}">
                    <div class="video-type-icon">
                        <i class="fas fa-video"></i>
                    </div>
                    <h6>${type.name}</h6>
                    <p class="text-muted small">${type.description}</p>
                    <div class="video-type-price">${type.price} ₽</div>
                </div>
            </div>
        `;
    });
    
    modalHtml += `
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>
                        <button type="button" class="btn btn-primary" id="addSelectedToCart" disabled>Добавить в корзину</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal if any
    $('#videoTypeModal').remove();
    
    // Add modal to body
    $('body').append(modalHtml);
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('videoTypeModal'));
    modal.show();
    
    // Bind events
    $('.video-type-card').click(function() {
        $('.video-type-card').removeClass('selected');
        $(this).addClass('selected');
        $('#addSelectedToCart').prop('disabled', false);
    });
    
    $('#addSelectedToCart').click(function() {
        const selectedCard = $('.video-type-card.selected');
        if (selectedCard.length) {
            const typeId = selectedCard.data('type-id');
            const price = selectedCard.data('price');
            const typeName = selectedCard.find('h6').text();
            
            const cartItem = {
                athleteId: athleteId,
                athleteName: athleteName,
                eventId: eventId,
                eventName: eventName,
                categoryId: categoryId,
                categoryName: categoryName,
                videoTypeId: typeId,
                videoTypeName: typeName,
                price: price,
                quantity: 1
            };
            
            addToCart(cartItem);
            modal.hide();
        }
    });
}

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
