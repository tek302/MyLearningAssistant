package com.example.learning.agent.data.remote

import retrofit2.Response
import retrofit2.http.POST

/**
 * Backend /me API. Requires Authorization: Bearer <token>.
 */
interface MeApi {

    @POST("me/trigger-worker")
    suspend fun triggerWorker(): Response<TriggerWorkerResponse>

    data class TriggerWorkerResponse(
        val status: String,
        val processed: Boolean,
        val job_id: String? = null
    )
}
