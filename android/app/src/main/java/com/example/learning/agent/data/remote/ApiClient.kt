package com.example.learning.agent.data.remote

import com.example.learning.agent.BuildConfig
import com.google.gson.GsonBuilder
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {

    private val okHttp = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .addInterceptor(AuthInterceptor())
        .apply {
            if (BuildConfig.DEBUG) {
                addInterceptor(HttpLoggingInterceptor().setLevel(HttpLoggingInterceptor.Level.BODY))
            }
        }
        .build()

    private val retrofit = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .client(okHttp)
        .addConverterFactory(GsonConverterFactory.create(GsonBuilder().create()))
        .build()

    val ingestApi: IngestApi = retrofit.create(IngestApi::class.java)
    val documentsApi: DocumentsApi = retrofit.create(DocumentsApi::class.java)
    val notesApi: NotesApi = retrofit.create(NotesApi::class.java)
    val feedbackApi: FeedbackApi = retrofit.create(FeedbackApi::class.java)
    val ragApi: RagApi = retrofit.create(RagApi::class.java)
    val meApi: MeApi = retrofit.create(MeApi::class.java)
    val s2Api: S2Api = retrofit.create(S2Api::class.java)
    val recommendationsApi: RecommendationsApi = retrofit.create(RecommendationsApi::class.java)
    val keywordsApi: KeywordsApi = retrofit.create(KeywordsApi::class.java)
}
