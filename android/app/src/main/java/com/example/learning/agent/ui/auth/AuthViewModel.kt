package com.example.learning.agent.ui.auth

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.learning.agent.BuildConfig
import com.example.learning.agent.R
import com.example.learning.agent.data.auth.TokenProvider
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInOptions
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.GoogleAuthProvider
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

data class AuthState(
    val isSignedIn: Boolean = false,
    val userEmail: String? = null,
    val isLoading: Boolean = false,
    val errorMessage: String? = null
)

class AuthViewModel(application: Application) : AndroidViewModel(application) {

    private val firebaseAuth = FirebaseAuth.getInstance()
    private val tokenProvider = TokenProvider

    private val webClientId = application.getString(R.string.default_web_client_id)

    private val gso = GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
        .requestIdToken(webClientId)
        .requestEmail()
        .build()

    val googleSignInClient = GoogleSignIn.getClient(application, gso)

    private val _authState = MutableStateFlow(AuthState())
    val authState: StateFlow<AuthState> = _authState.asStateFlow()

    init {
        firebaseAuth.addAuthStateListener { auth ->
            val user = auth.currentUser
            _authState.value = _authState.value.copy(
                isSignedIn = user != null,
                userEmail = user?.email,
                errorMessage = null
            )
        }
        // Initial state from current user
        _authState.value = _authState.value.copy(
            isSignedIn = firebaseAuth.currentUser != null,
            userEmail = firebaseAuth.currentUser?.email
        )
    }

    fun handleSignInResult(idToken: String?) {
        if (idToken == null) {
            _authState.value = _authState.value.copy(
                errorMessage = "Sign-in was cancelled or failed.",
                isLoading = false
            )
            return
        }
        viewModelScope.launch {
            _authState.value = _authState.value.copy(isLoading = true, errorMessage = null)
            runCatching {
                val credential = GoogleAuthProvider.getCredential(idToken, null)
                firebaseAuth.signInWithCredential(credential).await()
            }.onSuccess { authResult ->
                _authState.value = _authState.value.copy(
                    isSignedIn = true,
                    userEmail = authResult.user?.email,
                    isLoading = false,
                    errorMessage = null
                )
                // Log the full ID token only in debug builds
                if (BuildConfig.DEBUG) {
                    authResult.user?.getIdToken(true)?.addOnSuccessListener { result ->
                        result.token?.let { token ->
                            Log.d("AUTH_FULL_TOKEN", token)
                        }
                    }
                }
            }.onFailure { e ->
                _authState.value = _authState.value.copy(
                    isLoading = false,
                    errorMessage = "Sign-in failed: ${e.message}"
                )
            }
        }
    }

    fun signOut() {
        tokenProvider.clearCache()
        googleSignInClient.signOut()
        firebaseAuth.signOut()
        _authState.value = AuthState()
    }

    fun clearError() {
        _authState.value = _authState.value.copy(errorMessage = null)
    }
}
