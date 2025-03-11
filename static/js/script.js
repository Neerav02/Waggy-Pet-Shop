(function($) {

  "use strict";

  var initPreloader = function() {
    $(document).ready(function() {
      $('body').addClass('preloader-site');
    });

    $(window).on('load', function() {
      $('.preloader-wrapper').fadeOut();
      $('body').removeClass('preloader-site');
    });
  }

  // init Chocolat light box
	var initChocolat = function() {
		Chocolat(document.querySelectorAll('.image-link'), {
		  imageSize: 'contain',
		  loop: true,
		})
	}

  var initSwiper = function() {
    if (typeof Swiper !== 'undefined') {
      // Hero Slider
      new Swiper(".hero-slider", {
        loop: true,
        autoplay: {
          delay: 5000,
          disableOnInteraction: false,
        },
        pagination: {
          el: ".swiper-pagination",
          clickable: true,
        },
        navigation: {
          nextEl: ".swiper-button-next",
          prevEl: ".swiper-button-prev",
        },
      });

      // Featured Products Slider
      new Swiper(".featured-slider", {
        slidesPerView: 1,
        spaceBetween: 20,
        loop: true,
        autoplay: {
          delay: 3000,
          disableOnInteraction: false,
        },
        navigation: {
          nextEl: ".swiper-button-next",
          prevEl: ".swiper-button-prev",
        },
        breakpoints: {
          640: {
            slidesPerView: 2,
          },
          768: {
            slidesPerView: 3,
          },
          1024: {
            slidesPerView: 4,
          },
        },
      });

      // Bestselling Products Slider
      new Swiper(".bestselling-swiper", {
        slidesPerView: 4,
        spaceBetween: 30,
        speed: 500,
        breakpoints: {
          0: {
            slidesPerView: 1,
          },
          768: {
            slidesPerView: 3,
          },
          991: {
            slidesPerView: 4,
          },
        }
      });

      // Testimonials Slider
      new Swiper(".testimonial-swiper", {
        slidesPerView: 1,
        speed: 500,
        pagination: {
          el: ".swiper-pagination",
          clickable: true,
        },
      });

      // Product thumbnails slider
      if ($('.product-thumbnail-slider').length > 0) {
        var thumb_slider = new Swiper(".product-thumbnail-slider", {
          spaceBetween: 8,
          slidesPerView: 3,
          freeMode: true,
          watchSlidesProgress: true,
        });

        var large_slider = new Swiper(".product-large-slider", {
          spaceBetween: 10,
          slidesPerView: 1,
          effect: 'fade',
          thumbs: {
            swiper: thumb_slider,
          },
        });
      }
    }
  }

  var initProductQty = function(){

    $('.product-qty').each(function(){

      var $el_product = $(this);
      var quantity = 0;

      $el_product.find('.quantity-right-plus').click(function(e){
          e.preventDefault();
          var quantity = parseInt($el_product.find('#quantity').val());
          $el_product.find('#quantity').val(quantity + 1);
      });

      $el_product.find('.quantity-left-minus').click(function(e){
          e.preventDefault();
          var quantity = parseInt($el_product.find('#quantity').val());
          if(quantity>0){
            $el_product.find('#quantity').val(quantity - 1);
          }
      });

    });

  }

  // init jarallax parallax
  var initJarallax = function() {
    jarallax(document.querySelectorAll(".jarallax"));

    jarallax(document.querySelectorAll(".jarallax-keep-img"), {
      keepImg: true,
    });
  }

  var initIsotope = function() {
    // Wait for images to load before initializing Isotope
    $(window).on('load', function() {
      if ($('.isotope-container').length > 0) {
        $('.isotope-container').isotope({
          itemSelector: '.item',
          layoutMode: 'masonry'
        });
      }

      if ($('.entry-container').length > 0) {
        $('.entry-container').isotope({
          itemSelector: '.entry-item',
          layoutMode: 'masonry'
        });
      }

      // Filter button click handler
      $('.filter-button').on('click', function() {
        var filterValue = $(this).attr('data-filter');
        $('.filter-button').removeClass('active');
        $(this).addClass('active');
        
        $('.isotope-container').isotope({
          filter: filterValue === '*' ? '*' : filterValue
        });
      });
    });
  }

  // document ready
  $(document).ready(function() {
    
    initPreloader();
    initSwiper();
    initProductQty();
    if (typeof jarallax !== 'undefined') {
      initJarallax();
    }
    if (typeof Chocolat !== 'undefined') {
      initChocolat();
    }
    initIsotope();

  }); // End of a document

})(jQuery);

document.addEventListener('DOMContentLoaded', function() {
    // Add preloader class to body
    document.body.classList.add('preloader-site');

    // Remove preloader when page is loaded
    window.addEventListener('load', function() {
        const preloader = document.querySelector('.preloader-wrapper');
        if (preloader) {
            preloader.style.display = 'none';
            document.body.classList.remove('preloader-site');
        }
    });

    // Initialize other functions if needed
    initSwiper();
});

// Initialize Swiper
function initSwiper() {
    // Hero Slider
    new Swiper('.hero-slider', {
        loop: true,
        autoplay: {
            delay: 5000,
            disableOnInteraction: false,
        },
        pagination: {
            el: '.swiper-pagination',
            clickable: true,
        },
        navigation: {
            nextEl: '.swiper-button-next',
            prevEl: '.swiper-button-prev',
        },
    });

    // Featured Products Slider
    new Swiper('.featured-slider', {
        slidesPerView: 1,
        spaceBetween: 20,
        loop: true,
        autoplay: {
            delay: 3000,
            disableOnInteraction: false,
        },
        navigation: {
            nextEl: '.swiper-button-next',
            prevEl: '.swiper-button-prev',
        },
        breakpoints: {
            640: {
                slidesPerView: 2,
            },
            768: {
                slidesPerView: 3,
            },
            1024: {
                slidesPerView: 4,
            },
        },
    });
}

// Call initSwiper when document is ready
document.addEventListener('DOMContentLoaded', function() {
    initSwiper();
});

// Add to Cart functionality
function addToCart(productId) {
    const quantity = document.getElementById('quantity') ? parseInt(document.getElementById('quantity').value) : 1;
    
    fetch('/cart/add/' + productId, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ quantity: quantity })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Show success message
            const toast = document.createElement('div');
            toast.className = 'toast align-items-center text-white bg-dark border-0 position-fixed bottom-0 end-0 m-3';
            toast.setAttribute('role', 'alert');
            toast.setAttribute('aria-live', 'assertive');
            toast.setAttribute('aria-atomic', 'true');
            toast.innerHTML = `
                <div class="d-flex">
                    <div class="toast-body">
                        Product added to cart successfully!
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
            `;
            document.body.appendChild(toast);
            const bsToast = new bootstrap.Toast(toast);
            bsToast.show();
            
            // Update cart count
            updateCartCount();
            
            // Remove toast after it's hidden
            toast.addEventListener('hidden.bs.toast', function () {
                toast.remove();
            });
        } else {
            if (data.error === 'Please login to add items to cart') {
                // Show login required message
                const toast = document.createElement('div');
                toast.className = 'toast align-items-center text-white bg-dark border-0 position-fixed bottom-0 end-0 m-3';
                toast.setAttribute('role', 'alert');
                toast.setAttribute('aria-live', 'assertive');
                toast.setAttribute('aria-atomic', 'true');
                toast.innerHTML = `
                    <div class="d-flex">
                        <div class="toast-body">
                            Please login to add items to cart
                        </div>
                        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                    </div>
                `;
                document.body.appendChild(toast);
                const bsToast = new bootstrap.Toast(toast);
                bsToast.show();
                
                // Redirect to login page after a short delay
                setTimeout(() => {
                    window.location.href = '/login';
                }, 1500);
            } else {
                alert(data.error || 'Error adding product to cart');
            }
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error adding product to cart');
    });
}

// Update cart count in navbar
function updateCartCount() {
    fetch('/cart/count')
    .then(response => response.json())
    .then(data => {
        const cartBadge = document.querySelector('.badge');
        if (cartBadge) {
            cartBadge.textContent = data.count;
        }
    })
    .catch(error => {
        console.error('Error updating cart count:', error);
    });
}

// Filter products by category
function filterProducts(category) {
    const products = document.querySelectorAll('.product-card');
    products.forEach(product => {
        if (category === 'all' || product.dataset.category === category) {
            product.style.display = 'block';
        } else {
            product.style.display = 'none';
        }
    });

    // Update active button
    document.querySelectorAll('.btn-group .btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.textContent === category || (category === 'all' && btn.textContent === 'All')) {
            btn.classList.add('active');
        }
    });
}