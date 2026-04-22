// Cart functionality
function addToCart(productId) {
    fetch('/api/cart/add', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            product_id: productId,
            quantity: 1
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.message) {
            typeof showToast === 'function' ? showToast('Product added to cart!', 'success') : alert('Product added to cart!');
        } else if (data.error) {
            typeof showToast === 'function' ? showToast(data.error, 'danger') : alert(data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        typeof showToast === 'function' ? showToast('Error adding product to cart', 'danger') : alert('Error adding product to cart');
    });
}

function removeFromCart(productId) {
    fetch('/api/cart/remove', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            product_id: productId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.message) {
            // Reload the page to update cart
            window.location.reload();
        }
    })
    .catch(error => {
        console.error('Error:', error);
        typeof showToast === 'function' ? showToast('Error removing product from cart', 'danger') : alert('Error removing product from cart');
    });
}