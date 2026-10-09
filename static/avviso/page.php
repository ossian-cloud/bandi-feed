<?php
// Serves avviso/<id>.html from the gzipped JSON shard built by build.py. Reads only its own files; stores nothing.
$id = $_GET['id'] ?? '';
$html = null;
if (preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/', $id)) {
    $raw = @file_get_contents(__DIR__ . '/data/' . $id[0] . '.json.gz');
    $pages = $raw === false ? null : json_decode(gzdecode($raw), true);
    $html = $pages[$id] ?? null;
}
header('Content-Type: text/html; charset=utf-8');
if ($html === null) {
    http_response_code(404);
    $html = @file_get_contents(__DIR__ . '/data/404.html') ?: 'Avviso non trovato.';
} else {
    header('Cache-Control: max-age=900');
}
echo $html;
