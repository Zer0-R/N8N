const k = require('./vocabag_correcteur.js');
const fs = require('fs');
const ar = JSON.parse(fs.readFileSync('/var/www/muz-video-template/channels/vocabag/videos/20261004_150054_phrase_ar_work_studies_words.json'))[0].reveals;
const nl = JSON.parse(fs.readFileSync('/var/www/muz-video-template/channels/vocabag/videos/20261003_150023_phrase_nl_home_interior_words.json'))[0].reveals;
const es = [{ word: 'casa', transliteration: '', translation: 'maison', example_sentence: 'La casa de mi madre es grande.', example_translation: 'La maison de ma mère est grande.', answerDisplay: 'La casa de mi madre es grande.' }];
const zh = [{ word: '茶', transliteration: 'chá', translation: 'thé', example_sentence: '我喜欢喝茶。', example_translation: "J'aime boire du thé.", answerDisplay: 'Wǒ xǐhuān hē chá\n(J’aime boire du thé.)' }];
const hao = [{ word: '好', transliteration: 'hǎo', translation: 'bien', example_sentence: '今天天气很好。', example_translation: 'Il fait beau aujourd’hui.', answerDisplay: 'Jīntiān tiānqì hěn hǎo' }];
const fr = [{ word: 'chat', transliteration: '', translation: 'chat', example_sentence: 'Elle a deux chats.', example_translation: 'Elle a deux chats.', answerDisplay: 'Elle a deux chats.' }];
const pe = [{ word: 'perro', transliteration: '', translation: 'chien', example_sentence: 'Es mi perro.', example_translation: "C'est mon chien.", answerDisplay: 'Es mi perro.' }];
const T = [
  [hao, '我不好意思', null], [hao, '好', 'bravo'], [hao, '今天天气很好', 'bravo'],
  [fr, 'elle deux chats', 'presque'], [fr, 'Elle a deux chats', 'bravo'], [fr, 'deux', null],
  [pe, 'Es mi perro', 'bravo'], [pe, 'es mi', null], [pe, 'perro', 'bravo'],
  [es, 'Je suis de la région, trop bien', null], [es, 'La casa de mi madre es grande', 'bravo'], [es, 'la casa de mi madre', 'presque'],
  [es, 'casa', 'bravo'], [es, 'de la', null],
  [zh, '我喜欢喝茶', 'bravo'], [zh, '我喜欢', 'presque'], [zh, 'wo xihuan he cha', 'bravo'], [zh, '茶', 'bravo'], [zh, '好看', null],
  [ar, 'المدير يعمل في مكتب كبير بالعمارة', 'bravo'], [ar, 'al mudir yamal fi maktab kabir bil imara', 'bravo'],
  [ar, 'al-mudir yaʿmal fi maktab kabir', 'presque'], [ar, 'Maktab', 'bravo'], [ar, 'super vidéo merci 🙏', null], [ar, 'في', null],
  [nl, 'Bel aan de deurbel', 'bravo'], [nl, 'Het eten is in de ijskast!', 'bravo'], [nl, 'het eten in ijskast', 'presque'],
  [nl, 'Trop bien cette appli', null], [nl, 'de', null],
];
let ko = 0;
for (const [rev, t, attendu] of T) {
  const ev = k.evaluer(t, k.candidats(rev)); const got = ev ? ev.type : null;
  if (got !== attendu) ko++;
  console.log(got === attendu ? 'OK ' : 'KO ', JSON.stringify(t).padEnd(44), '→', got, ev ? ev.score.toFixed(2) + ' | ' + k.reponse(ev) : '');
}
console.log(ko ? `${ko} échec(s)` : 'tous les cas passent');
