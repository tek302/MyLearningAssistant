package com.example.learning.agent.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.ui.graphics.vector.ImageVector

sealed class Destination(
    val route: String,
    val label: String,
    val icon: ImageVector
) {
    object Feed : Destination("feed", "Feed", Icons.Filled.Home)
    object Ask : Destination("ask", "Ask", Icons.Filled.QuestionAnswer)
    object Notes : Destination("notes", "Notes", Icons.Filled.Note)
    object Map : Destination("map", "Map", Icons.Filled.Map)
    object Recommendations : Destination("recommendations", "Recommendations", Icons.Filled.Star)

    // Detail screens
    object FeedDetail : Destination("feed_detail/{id}", "Feed Detail", Icons.Filled.Article) {
        fun createRoute(id: String) = "feed_detail/$id"
    }
}

val bottomNavItems = listOf(
    Destination.Feed,
    Destination.Ask,
    Destination.Notes,
    Destination.Map,
    Destination.Recommendations
)

