/**
 * Tracker d'activite visiteur - ValoMaison
 * Avec gestion du consentement RGPD
 */

(function() {
    'use strict';

    // === MOBILE MENU TOGGLE ===
    var navToggle = document.querySelector('.nav-toggle');
    if (navToggle) {
        navToggle.addEventListener('click', function() {
            var navLinks = document.querySelector('.nav-links');
            if (navLinks) {
                navLinks.classList.toggle('active');
                this.textContent = this.textContent === '☰' ? '✕' : '☰';
            }
        });
    }

    // === UTILITAIRES ===

    function generateId() {
        return 'xxxx-xxxx-xxxx'.replace(/x/g, function() {
            return Math.floor(Math.random() * 16).toString(16);
        });
    }

    // Envoyer des donnees JSON (avec sendBeacon ou XHR)
    function sendData(url, data) {
        var jsonStr = JSON.stringify(data);

        if (navigator.sendBeacon) {
            // Utiliser un Blob pour avoir le bon Content-Type
            var blob = new Blob([jsonStr], { type: 'application/json' });
            navigator.sendBeacon(url, blob);
        } else {
            var xhr = new XMLHttpRequest();
            xhr.open('POST', url, true);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.send(jsonStr);
        }
    }

    // === GESTION DU CONSENTEMENT ===

    var CONSENT_KEY = 'ei_consent';

    function getConsent() {
        return localStorage.getItem(CONSENT_KEY);
    }

    function setConsent(value) {
        localStorage.setItem(CONSENT_KEY, value);
    }

    function hasConsent() {
        return getConsent() === 'accepted';
    }

    function hasDecided() {
        var consent = getConsent();
        return consent === 'accepted' || consent === 'refused';
    }

    // Enregistrer le consentement en base
    function recordConsent(accepted) {
        var visitorId = localStorage.getItem('ei_visitor') || generateId();
        localStorage.setItem('ei_visitor', visitorId);

        var consentText = 'Nous utilisons des cookies et traceurs pour analyser votre navigation et ameliorer nos services. Vos donnees peuvent etre partagees avec nos partenaires.';

        var data = {
            visitor_id: visitorId,
            consent_type: 'cookies',
            consent_value: accepted,
            consent_text: consentText,
            page_url: window.location.href
        };

        sendData('/api/consent', data);
    }

    // Creer la banniere cookies
    function createCookieBanner() {
        if (document.getElementById('cookie-banner')) return;

        var banner = document.createElement('div');
        banner.id = 'cookie-banner';
        banner.className = 'cookie-banner';
        banner.innerHTML =
            '<div class="cookie-content">' +
                '<div class="cookie-text">' +
                    '<p>Nous utilisons des cookies et traceurs pour analyser votre navigation et ameliorer nos services. ' +
                    'Vos donnees peuvent etre partagees avec nos partenaires. ' +
                    '<a href="/politique-confidentialite">En savoir plus</a></p>' +
                '</div>' +
                '<div class="cookie-buttons">' +
                    '<button class="cookie-btn cookie-btn-refuse" id="cookie-refuse">Refuser</button>' +
                    '<button class="cookie-btn cookie-btn-accept" id="cookie-accept">Accepter</button>' +
                '</div>' +
            '</div>';

        document.body.appendChild(banner);

        // Afficher avec animation
        setTimeout(function() {
            banner.classList.add('show');
        }, 500);

        // Event listeners
        document.getElementById('cookie-accept').addEventListener('click', function() {
            setConsent('accepted');
            recordConsent(true);  // Enregistrer en DB
            banner.classList.remove('show');
            setTimeout(function() {
                banner.remove();
            }, 300);
            // Demarrer le tracking
            initTracking();
        });

        document.getElementById('cookie-refuse').addEventListener('click', function() {
            setConsent('refused');
            recordConsent(false);  // Enregistrer en DB
            banner.classList.remove('show');
            setTimeout(function() {
                banner.remove();
            }, 300);
        });
    }

    // === TRACKING ===

    var sessionId, visitorId, pageStartTime, maxScrollDepth, lastFormStep, lastFormField;

    // Tracking anonyme (sans consentement) - IP tronquée côté serveur
    function trackAnonymous(eventType, extraData) {
        var data = {
            event_type: eventType,
            page_path: window.location.pathname,
            timestamp: new Date().toISOString(),
            consent: hasConsent() ? 'full' : 'anonymous'
        };

        if (extraData) {
            data.extra_data = extraData;
        }

        // Toujours envoyer, le serveur gère l'anonymisation
        sendData('/api/track-step', data);
    }

    // Tracking des étapes du formulaire (fonctionne sans consentement)
    function trackFormStep(step, stepName, formData) {
        console.log('[Tracker] Step ' + step + ': ' + stepName);
        trackAnonymous('form_step', {
            step: step,
            step_name: stepName,
            form_data: formData || {}
        });
    }

    function track(eventType, extraData) {
        if (!hasConsent()) return;

        var data = {
            session_id: sessionId,
            visitor_id: visitorId,
            event_type: eventType,
            page_url: window.location.href,
            page_path: window.location.pathname,
            referrer: document.referrer || null,
            screen_width: window.innerWidth,
            screen_height: window.innerHeight,
            time_on_page: Math.round((Date.now() - pageStartTime) / 1000)
        };

        if (extraData) {
            data.extra_data = extraData;
        }

        sendData('/api/track', data);
    }

    function initTracking() {
        // IDs
        sessionId = sessionStorage.getItem('ei_session') || generateId();
        sessionStorage.setItem('ei_session', sessionId);

        visitorId = localStorage.getItem('ei_visitor') || generateId();
        localStorage.setItem('ei_visitor', visitorId);

        pageStartTime = Date.now();
        maxScrollDepth = 0;
        lastFormStep = 0;
        lastFormField = '';

        // Pageview
        track('pageview');

        // Clics
        document.addEventListener('click', function(e) {
            var target = e.target;

            while (target && target !== document.body) {
                if (target.classList && (
                    target.classList.contains('cta-button') ||
                    target.classList.contains('btn-primary') ||
                    target.classList.contains('btn-cta') ||
                    target.tagName === 'BUTTON' ||
                    (target.tagName === 'A' && target.href)
                )) {
                    track('click', {
                        element_id: target.id || null,
                        element_text: (target.innerText || '').substring(0, 100),
                        element_class: target.className || null
                    });
                    break;
                }
                target = target.parentElement;
            }
        });

        // Scroll
        var scrollTimeout;
        window.addEventListener('scroll', function() {
            clearTimeout(scrollTimeout);
            scrollTimeout = setTimeout(function() {
                var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
                var docHeight = document.documentElement.scrollHeight - window.innerHeight;
                var scrollPercent = Math.round((scrollTop / docHeight) * 100);

                if (scrollPercent > maxScrollDepth) {
                    var oldPalier = Math.floor(maxScrollDepth / 25);
                    var newPalier = Math.floor(scrollPercent / 25);

                    if (newPalier > oldPalier) {
                        maxScrollDepth = scrollPercent;
                        track('scroll', { scroll_depth: newPalier * 25 });
                    }
                }
            }, 200);
        });

        // Formulaires
        document.addEventListener('change', function(e) {
            var target = e.target;
            if (target.tagName === 'INPUT' || target.tagName === 'SELECT' || target.tagName === 'TEXTAREA') {
                var fieldName = target.name || target.id || 'unknown';
                if (fieldName !== lastFormField) {
                    lastFormField = fieldName;
                    track('form_field', { form_field: fieldName });
                }
            }
        });

        document.addEventListener('submit', function(e) {
            var form = e.target;
            track('form_submit', {
                element_id: form.id || null,
                form_step: lastFormStep || 1
            });
        });

        // Depart
        window.addEventListener('beforeunload', function() {
            track('page_leave', {
                scroll_depth: maxScrollDepth,
                form_step: lastFormStep || null
            });
        });
    }

    // === INITIALISATION ===

    if (hasDecided()) {
        if (hasConsent()) {
            initTracking();
        }
        // Si refuse, on ne fait rien
    } else {
        // Afficher la banniere
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', createCookieBanner);
        } else {
            createCookieBanner();
        }
    }

    // Exposer pour usage manuel
    window.EITracker = {
        track: track,
        trackFormStep: trackFormStep,
        trackAnonymous: trackAnonymous,
        hasConsent: hasConsent,
        getConsent: getConsent
    };

})();
