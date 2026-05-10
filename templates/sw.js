// sw.js - Service Worker для push-уведомлений
self.addEventListener('push', function(event) {
    console.log('Push event received');
    let data;
    try {
        data = event.data.json();
    } catch (e) {
        data = { title: 'TaskMentor', body: 'Новое уведомление' };
    }
    const options = {
        body: data.body,
        icon: data.icon || '/static/images/icon.png',
        badge: data.badge || '/static/images/badge.png',
        data: data.data || {},
        vibrate: [200, 100, 200],
        requireInteraction: true,
    };
    event.waitUntil(self.registration.showNotification(data.title, options));
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    const url = event.notification.data.url || '/';
    event.waitUntil(clients.openWindow(url));
});