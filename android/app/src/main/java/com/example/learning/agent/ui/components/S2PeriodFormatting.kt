package com.example.learning.agent.ui.components

import com.example.learning.agent.data.remote.S2Api
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

private val s2DateDisplayFmt: DateTimeFormatter =
    DateTimeFormatter.ofPattern("MMM d, yyyy", Locale.US)

/** Human-readable inclusive ET range when BE sends period_* fields; null for legacy rows. */
fun formatS2PeriodLine(extra: S2Api.S2Extra?): String? {
    val start = extra?.periodStartEt ?: return null
    val end = extra?.periodEndEtInclusive ?: return null
    val a = runCatching { LocalDate.parse(start).format(s2DateDisplayFmt) }.getOrNull() ?: start
    val b = runCatching { LocalDate.parse(end).format(s2DateDisplayFmt) }.getOrNull() ?: end
    val tz = extra.periodTz?.let { tz ->
        when (tz) {
            "America/New_York" -> "ET"
            else -> tz
        }
    }
    return if (tz != null) "$a – $b ($tz)" else "$a – $b"
}
