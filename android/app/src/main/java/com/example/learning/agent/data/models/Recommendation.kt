package com.example.learning.agent.data.models

data class Recommendation(
    val id: String,
    val title: String,
    val source: String,
    val date: String,
    val score: Float, // 0.0 to 1.0
    val topic: String
)

