<?php
header('Content-Type: application/json; charset=utf-8');

// Pfad zu einer Datei, in der wir unsere Zähler speichern.
// Achtung: Auf ausreichende Schreibrechte achten!
$counterFile = __DIR__ . '/counts.json';

// 1) Aktuell gespeicherte Zählerstände laden oder Standardwerte nehmen
if (!file_exists($counterFile)) {
    $counts = array("video" => 0, "gpx" => 0);
} else {
    $jsonContent = file_get_contents($counterFile);
    $counts = json_decode($jsonContent, true);
    if (!is_array($counts)) {
        $counts = array("video" => 0, "gpx" => 0);
    }
}

// 2) Anhand der GET-Parameter entscheiden wir, was zu tun ist
//    ?action=increment_video  => Video-Zähler +1
//    ?action=increment_gpx    => GPX-Zähler +1
//    ?action=... (leer)       => nur Werte zurückgeben (kein Hochzählen)
$action = isset($_GET['action']) ? $_GET['action'] : '';

if ($action === 'increment_video') {
    $counts['video']++;
} elseif ($action === 'increment_gpx') {
    $counts['gpx']++;
}

// 3) Neue Werte wieder in counts.json speichern
file_put_contents($counterFile, json_encode($counts));

// 4) Aktuellen Stand als JSON ausgeben
echo json_encode($counts, JSON_PRETTY_PRINT);
