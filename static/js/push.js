// static/js/push.js
(async () => {
    console.log('push.js started');

    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        console.error('Push not supported by this browser');
        return;
    }

    // 1. Регистрация Service Worker
    const swUrl = window.SW_URL || '/static/js/sw.js';
    let registration;
    try {
        registration = await navigator.serviceWorker.register(swUrl);
        console.log('Service Worker registered:', swUrl);
    } catch (err) {
        console.error('Service Worker registration failed:', err);
        return;
    }

    // 2. Проверка разрешения на уведомления
    let permission = Notification.permission;
    if (permission !== 'granted') {
        permission = await Notification.requestPermission();
    }
    if (permission !== 'granted') {
        console.warn('Notification permission denied or not granted');
        return;
    }

    // 3. Получение VAPID публичного ключа с сервера
    let publicKey;
    try {
        const resp = await fetch('/core/push/vapid-key/');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        publicKey = data.key;
        if (!publicKey || publicKey === '') {
            throw new Error('VAPID key is empty');
        }
        console.log('VAPID key received, length:', publicKey.length);
    } catch (err) {
        console.error('Failed to get VAPID key:', err);
        return;
    }

    // 4. Создание подписки
    let subscription;
    try {
        subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(publicKey)
        });
        console.log('Push subscription created', subscription);
    } catch (err) {
        console.error('Push subscription failed:', err);
        return;
    }

    // 5. Получение CSRF-токена из мета-тега (наиболее надёжный способ)
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    console.log('CSRF token length:', csrfToken ? csrfToken.length : 'missing');

    if (!csrfToken) {
        console.error('CSRF token not found in meta tag');
        return;
    }

    // 6. Отправка подписки на сервер
    try {
        const response = await fetch('/core/push/subscribe/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(subscription)
        });
        if (response.ok) {
            console.log('Push subscription sent to server successfully');
        } else {
            const text = await response.text();
            console.error('Server returned error:', response.status, text);
        }
    } catch (err) {
        console.error('Failed to send subscription:', err);
    }
})();

// Вспомогательные функции
function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}