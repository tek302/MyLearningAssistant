package com.example.learning.agent.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Article
import androidx.compose.material.icons.automirrored.filled.Note
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.QuestionAnswer
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Summarize
import androidx.compose.ui.graphics.vector.ImageVector

sealed class Destination(
    val route: String,
    val label: String,
    val icon: ImageVector
) {
    object Feed : Destination("feed", "Feed", Icons.Filled.Home)
    object Ask : Destination("ask", "Ask", Icons.Filled.QuestionAnswer)
    object Notes : Destination("notes", "Notes", Icons.AutoMirrored.Filled.Note)
    object Map : Destination("map", "Weekly", Icons.Filled.Summarize)
    object Recommendations : Destination("recommendations", "Recommendations", Icons.Filled.Star)

    // Detail screens (AutoMirrored.Article for RTL support)
    object FeedDetail : Destination("feed_detail/{id}", "Feed Detail", Icons.AutoMirrored.Filled.Article) {
        fun createRoute(id: String) = "feed_detail/$id"
    }
    object S2Detail : Destination("s2_detail/{id}", "Weekly Summary Detail", Icons.AutoMirrored.Filled.Article) {
        fun createRoute(id: String) = "s2_detail/$id"
    }
}

val bottomNavItems = listOf(
    Destination.Feed,
    Destination.Ask,
    Destination.Notes,
    Destination.Map,
    Destination.Recommendations
)

