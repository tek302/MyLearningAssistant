package com.example.learning.agent.data.remote

import com.google.gson.annotations.SerializedName
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

interface ThreadsApi {

    @GET("threads")
    suspend fun listThreads(): Response<ThreadsResponse>

    @POST("threads")
    suspend fun createThread(@Body body: CreateThreadRequest): Response<InterestThreadItem>

    @POST("threads/{threadId}/archive")
    suspend fun archiveThread(@Path("threadId") threadId: String): Response<Unit>

    data class ThreadsResponse(
        val threads: List<InterestThreadItem>
    )

    data class InterestThreadItem(
        val id: String,
        val name: String,
        val description: String? = null,
        @SerializedName("is_default") val isDefault: Boolean = false,
        @SerializedName("archived_at") val archivedAt: String? = null,
        @SerializedName("created_at") val createdAt: String? = null,
        @SerializedName("updated_at") val updatedAt: String? = null
    )

    data class CreateThreadRequest(
        val name: String,
        val description: String? = null,
        @SerializedName("is_default") val isDefault: Boolean = false
    )
}
