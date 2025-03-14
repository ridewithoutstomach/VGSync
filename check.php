<?php
// check.php
// 1) Optionale Auth: z.B. einfacher Token
$secretToken = "SUPER_SECRET_123";
if (!isset($_GET['token']) || $_GET['token'] !== $secretToken) {
    http_response_code(403);
    echo "Forbidden";
    exit;
}

// 2) Datei laden
$filename = __DIR__ . "/../versioninfo/versioninfo.txt";
if (!file_exists($filename)) {
    http_response_code(500);
    echo "File not found";
    exit;
}

$content = file_get_contents($filename);

// 3) Ausgeben
header("Content-Type: text/plain");
echo $content;
?>
