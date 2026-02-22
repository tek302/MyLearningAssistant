# Firebase Auth setup (Google Sign-In)

1. **Add `google-services.json`**  
   Download from [Firebase Console](https://console.firebase.google.com) → Project settings → Your apps → Android app, and place it at:
   ```
   android/app/google-services.json
   ```

2. **Set Web client ID for Google Sign-In**  
   In Firebase Console: Authentication → Sign-in method → Google → Web SDK configuration → copy **Web client ID**.  
   In the app, set it in `app/src/main/res/values/strings.xml`:
   ```xml
   <string name="default_web_client_id" translatable="false">YOUR_WEB_CLIENT_ID.apps.googleusercontent.com</string>
   ```
   Replace `YOUR_WEB_CLIENT_ID.apps.googleusercontent.com` with your actual Web client ID.

3. **Backend base URL**  
   In `app/build.gradle.kts`, `API_BASE_URL` is set per build type (debug uses emulator `10.0.2.2:8000` by default). Change it for a physical device (use your PC IP) or for release.
