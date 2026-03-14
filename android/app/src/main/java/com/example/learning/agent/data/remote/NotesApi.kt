package com.example.learning.agent.data.remote

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * Backend notes API (GET /notes, POST /notes). Requires Authorization: Bearer <token>.
 * Supports notes with or without source_id (document); null = "Free note".
 */
interface NotesApi {

    @GET("notes")
    suspend fun getNotes(
        @Query("source_id") sourceId: String? = null,
        @Query("limit") limit: Int = 100,
        @Query("offset") offset: Int = 0
    ): Response<NotesResponse>

    @POST("notes")
    suspend fun createNote(@Body body: CreateNoteRequest): Response<NoteItem>

    @DELETE("notes/{note_id}")
    suspend fun deleteNote(@Path("note_id") noteId: String): Response<Unit>

    data class NotesResponse(val notes: List<NoteItem>)

    data class NoteItem(
        val id: String,
        val source_id: String? = null,
        val topic: String? = null,
        val content: String,
        val created_at: String? = null
    )

    data class CreateNoteRequest(
        val content: String,
        val source_id: String? = null,
        val topic: String? = null
    )
}
