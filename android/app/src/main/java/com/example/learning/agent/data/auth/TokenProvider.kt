package com.example.learning.agent.data.auth

import com.google.firebase.auth.FirebaseAuth
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import kotlinx.coroutines.Dispatchers

/**
 * Provides Firebase ID token for API calls. Caches token and refreshes when
 * expired (tokens typically valid ~1 hour; we refresh if older than 50 minutes).
 * Returns null if user is not signed in.
 */
object TokenProvider {
    private val firebaseAuth: FirebaseAuth = FirebaseAuth.getInstance()
    @Volatile
    private var cachedToken: String? = null

    @Volatile
    private var expiresAtMillis: Long = 0

    /** Refresh if token is older than 50 minutes (tokens ~1h lifetime). */
    private const val REFRESH_THRESHOLD_MS = 50 * 60 * 1000L

    /**
     * Returns a valid ID token string, or null if not signed in.
     * Uses cache when still valid; otherwise fetches fresh token.
     */
    suspend fun getToken(): String? = withContext(Dispatchers.IO) {
        val user = firebaseAuth.currentUser ?: return@withContext null
        val now = System.currentTimeMillis()
        if (cachedToken != null && now < expiresAtMillis) {
            return@withContext cachedToken
        }
        runCatching {
            val result = user.getIdToken(true).await()
            result.token
        }.onSuccess { token ->
            cachedToken = token
            // JWT exp is seconds; use 50 min from now as safe expiry for our cache
            expiresAtMillis = now + REFRESH_THRESHOLD_MS
        }.getOrNull()
    }

    /** Call when user signs out to clear cache. */
    fun clearCache() {
        cachedToken = null
        expiresAtMillis = 0
    }
}
