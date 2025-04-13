// Import Firebase
import { initializeApp } from "https://www.gstatic.com/firebasejs/9.22.2/firebase-app.js";
import { getAuth, createUserWithEmailAndPassword, signInWithEmailAndPassword, signOut } from "https://www.gstatic.com/firebasejs/9.22.2/firebase-auth.js";

// Your Firebase configuration - use the same from your existing config
const firebaseConfig = {
    apiKey: "AIzaSyA7SAyZdpZAS0vuihGuvu-esvGKkx0LXL0",
    authDomain: "task-management-66a56.firebaseapp.com",
    projectId: "task-management-66a56",
    storageBucket: "task-management-66a56.firebasestorage.app",
    messagingSenderId: "24323526353",
    appId: "1:24323526353:web:193356d904f8a846e1bff0",
    measurementId: "G-G9TN78H295"
};

window.addEventListener("load", function() {
    // Initialize Firebase
    const app = initializeApp(firebaseConfig);
    const auth = getAuth(app);
    
    console.log("Firebase authentication initialized");
    
    // Check if user is logged in
    updateUI(document.cookie);
    
    // Register button click handler
    const registerBtn = document.getElementById("register-btn");
    if (registerBtn) {
        registerBtn.addEventListener('click', function() {
            const email = document.getElementById("email").value;
            const password = document.getElementById("password").value;
            const confirmPassword = document.getElementById("confirm-password").value;
            
            // Basic validation
            if (!email || !password) {
                showError("Please enter both email and password.");
                return;
            }
            
            if (password !== confirmPassword) {
                showError("Passwords do not match.");
                return;
            }
            
            // Create user account
            createUserWithEmailAndPassword(auth, email, password)
                .then((userCredential) => {
                    // User created successfully
                    const user = userCredential.user;
                    
                    // Get token and redirect
                    user.getIdToken().then((token) => {
                        document.cookie = "token=" + token + ";path=/;SameSite=Strict";
                        window.location = "/";
                    });
                })
                .catch((error) => {
                    // Show error message
                    showError("Registration failed: " + error.message);
                    console.log(error.code + ": " + error.message);
                });
        });
    }
    
    // Login button click handler
    const loginBtn = document.getElementById("login-btn");
    if (loginBtn) {
        loginBtn.addEventListener('click', function() {
            const email = document.getElementById("email").value;
            const password = document.getElementById("password").value;
            
            // Basic validation
            if (!email || !password) {
                showError("Please enter both email and password.");
                return;
            }
            
            // Sign in user
            signInWithEmailAndPassword(auth, email, password)
                .then((userCredential) => {
                    // User logged in successfully
                    const user = userCredential.user;
                    console.log("Logged in");
                    
                    // Get token and redirect
                    user.getIdToken().then((token) => {
                        document.cookie = "token=" + token + ";path=/;SameSite=Strict";
                        window.location = "/";
                    });
                })
                .catch((error) => {
                    // Show error message
                    showError("Login failed: " + error.message);
                    console.log(error.code + ": " + error.message);
                });
        });
    }
    
    // Sign out button click handler
    const signOutBtn = document.getElementById("sign-out");
    if (signOutBtn) {
        signOutBtn.addEventListener('click', function() {
            signOut(auth)
                .then(() => {
                    // Remove token and redirect
                    document.cookie = "token=;path=/;SameSite=Strict;expires=Thu, 01 Jan 1970 00:00:00 GMT";
                    window.location = "/";
                })
                .catch((error) => {
                    console.log("Sign out error:", error);
                });
        });
    }
});

// Show error message
function showError(message) {
    const errorElement = document.getElementById("error-message");
    if (errorElement) {
        errorElement.style.display = "block";
        errorElement.querySelector("p").textContent = message;
    }
}

// Update UI based on authentication state
function updateUI(cookie) {
    const token = parseCookieToken(cookie);
    
    // Handle specific elements on different pages
    const loginBox = document.getElementById("login-box");
    const signOutBtn = document.getElementById("sign-out");
    
    if (token.length > 0) {
        // User is logged in
        if (loginBox) loginBox.hidden = true;
        if (signOutBtn) signOutBtn.hidden = false;
        
        // If we're on login or register page, redirect to home
        if (window.location.pathname === "/login" || window.location.pathname === "/register") {
            window.location = "/";
        }
    } else {
        // User is not logged in
        if (loginBox) loginBox.hidden = false;
        if (signOutBtn) signOutBtn.hidden = true;
    }
}

// Extract token from cookie
function parseCookieToken(cookie) {
    // Split the cookie out on the basis of the semi colon
    var strings = cookie.split(';');
    
    // Go through each of the strings
    for (let i = 0; i < strings.length; i++) {
        // Split the string based on the = sign. if the LHS is token then return the RHS immediately
        var temp = strings[i].split('=');
        if (temp[0].trim() === "token")
            return temp[1];
    }
    
    // If token wasn't in the cookie, return empty string
    return "";
}