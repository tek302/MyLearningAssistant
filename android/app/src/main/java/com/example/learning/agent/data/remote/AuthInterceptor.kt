package com.example.learning.agent.data.remote

import com.example.learning.agent.BuildConfig
import kotlinx.coroutines.runBlocking
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Interceptor
import okhttp3.Response
import java.io.IOException

/**
 * OkHttp interceptor that adds Authorization: Bearer <id_token> only for requests
 * to the configured backend (API_BASE_URL). Other domains are not modified.
 * Fails fast with a clear error if no token is available (user not signed in).
 */
class AuthInterceptor(
    private val tokenProvider: com.example.learning.agent.data.auth.TokenProvider = com.example.learning.agent.data.auth.TokenProvider
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val url = request.url

        // Only attach token for requests to our backend host.
        val baseUrl = BuildConfig.API_BASE_URL
        val baseHost = baseUrl.toHttpUrlOrNull()?.host ?: return chain.proceed(request)
        if (url.host != baseHost) {
            return chain.proceed(request)
        }

        val token = runBlocking { tokenProvider.getToken() }
        if (token == null) {
            throw IOException("Not signed in. Please sign in to call the API.")
        }

        if (BuildConfig.DEBUG) {
            // Log only a short substring; never log full token.
            val preview = token.take(20) + "…"
            android.util.Log.d(TAG, "Auth header attached (token preview: $preview)")
        }

        val newRequest = request.newBuilder()
            .header("Authorization", "Bearer $token")
            .build()
        return chain.proceed(newRequest)
    }

    private companion object {
        const val TAG = "AuthInterceptor"
    }
}
