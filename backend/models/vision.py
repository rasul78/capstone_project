"""
Sentinel AI — VisionNet v2 (Dual-Mode)

Режим 1: ImageNet (по умолчанию для predict)
  - Предобученный ResNet-50 (ImageNet V2 weights, ~76% top-1)
  - 1000 классов реальных объектов с русскими названиями
  - Работает сразу без обучения

Режим 2: CIFAR-10 (для страницы Обучение)
  - Кастомная VisionNet с ResBlock + SE Attention
  - 10 классов, требует обучения
"""

import os
import threading
from typing import List, Dict, Optional, Callable

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
from PIL import Image
from torchvision import datasets, transforms, models
from torch.utils.data import DataLoader


# ── Русские названия ImageNet классов ─────────────────────────
IMAGENET_RU = {
    'tench': 'линь (рыба)', 'goldfish': 'золотая рыбка', 'great white shark': 'большая белая акула',
    'tiger shark': 'тигровая акула', 'hammerhead': 'акула-молот', 'electric ray': 'электрический скат',
    'stingray': 'скат', 'cock': 'петух', 'hen': 'курица', 'ostrich': 'страус',
    'brambling': 'вьюрок', 'goldfinch': 'щегол', 'house finch': 'домовый вьюрок',
    'junco': 'юнко', 'indigo bunting': 'индиговый овсянковый', 'robin': 'малиновка',
    'bulbul': 'бюльбюль', 'jay': 'сойка', 'magpie': 'сорока', 'chickadee': 'гаичка',
    'water ouzel': 'оляпка', 'kite': 'коршун', 'bald eagle': 'белоголовый орлан',
    'vulture': 'гриф', 'great grey owl': 'серая неясыть', 'european fire salamander': 'огненная саламандра',
    'common newt': 'тритон', 'eft': 'молодой тритон', 'spotted salamander': 'пятнистая саламандра',
    'axolotl': 'аксолотль', 'bullfrog': 'лягушка-бык', 'tree frog': 'квакша',
    'tailed frog': 'хвостатая лягушка', 'loggerhead': 'логгерхед', 'leatherback turtle': 'кожистая черепаха',
    'mud turtle': 'иловая черепаха', 'terrapin': 'черепаха', 'box turtle': 'коробчатая черепаха',
    'banded gecko': 'полосатый геккон', 'common iguana': 'игуана', 'american chameleon': 'хамелеон',
    'whiptail': 'хлыстохвост', 'agama': 'агама', 'frilled lizard': 'плащеносная ящерица',
    'alligator lizard': 'аллигаторная ящерица', 'gila monster': 'ядозуб',
    'green lizard': 'зелёная ящерица', 'african chameleon': 'африканский хамелеон',
    'komodo dragon': 'комодский варан', 'african crocodile': 'африканский крокодил',
    'american alligator': 'американский аллигатор', 'triceratops': 'трицератопс',
    'thunder snake': 'земляная змея', 'ringneck snake': 'кольчатая змея',
    'hognose snake': 'свиноносая змея', 'green snake': 'зелёная змея',
    'king snake': 'королевская змея', 'garter snake': 'подвязочная змея',
    'water snake': 'водяная змея', 'vine snake': 'лозовая змея',
    'night snake': 'ночная змея', 'boa constrictor': 'боа констриктор',
    'rock python': 'скальный питон', 'indian cobra': 'индийская кобра',
    'green mamba': 'зелёная мамба', 'sea snake': 'морская змея',
    'horned viper': 'рогатая гадюка', 'diamondback': 'гремучая змея',
    'sidewinder': 'гремучник', 'trilobite': 'трилобит',
    'harvestman': 'сенокосец', 'scorpion': 'скорпион', 'black and gold garden spider': 'садовый паук',
    'barn spider': 'амбарный паук', 'garden spider': 'садовый паук',
    'black widow': 'чёрная вдова', 'tarantula': 'тарантул', 'wolf spider': 'паук-волк',
    'tick': 'клещ', 'centipede': 'сороконожка', 'black grouse': 'тетерев',
    'ptarmigan': 'куропатка', 'ruffed grouse': 'рябчик', 'prairie chicken': 'луговой тетерев',
    'peacock': 'павлин', 'quail': 'перепел', 'partridge': 'куропатка',
    'african grey': 'жако', 'macaw': 'ара', 'sulphur-crested cockatoo': 'какаду',
    'lorikeet': 'лорикет', 'coucal': 'кукаль', 'bee eater': 'щурка',
    'hornbill': 'птица-носорог', 'hummingbird': 'колибри', 'jacamar': 'якамар',
    'toucan': 'тукан', 'drake': 'кряква', 'red-breasted merganser': 'крохаль',
    'goose': 'гусь', 'black swan': 'чёрный лебедь', 'tusker': 'слон',
    'echidna': 'ехидна', 'platypus': 'утконос', 'wallaby': 'валлаби',
    'koala': 'коала', 'wombat': 'вомбат', 'jellyfish': 'медуза',
    'sea anemone': 'морской анемон', 'brain coral': 'мозговой коралл',
    'flatworm': 'плоский червь', 'nematode': 'нематода', 'conch': 'раковина',
    'snail': 'улитка', 'slug': 'слизень', 'sea slug': 'морской слизень',
    'chiton': 'хитон', 'chambered nautilus': 'наутилус', 'dungeness crab': 'краб',
    'rock crab': 'скальный краб', 'fiddler crab': 'скрипач', 'king crab': 'камчатский краб',
    'american lobster': 'американский омар', 'spiny lobster': 'лангуст',
    'crayfish': 'речной рак', 'hermit crab': 'рак-отшельник', 'isopod': 'равноногий рак',
    'white stork': 'белый аист', 'black stork': 'чёрный аист', 'spoonbill': 'колпица',
    'flamingo': 'фламинго', 'little blue heron': 'цапля', 'american egret': 'белая цапля',
    'bittern': 'выпь', 'crane': 'журавль', 'limpkin': 'арама', 'european gallinule': 'камышница',
    'american coot': 'лысуха', 'bustard': 'дрофа', 'ruddy turnstone': 'камнешарка',
    'red-backed sandpiper': 'кулик', 'redshank': 'красноножка', 'dowitcher': 'бекасовидный веретенник',
    'oystercatcher': 'кулик-сорока', 'pelican': 'пеликан', 'king penguin': 'королевский пингвин',
    'albatross': 'альбатрос', 'grey whale': 'серый кит', 'killer whale': 'косатка',
    'dugong': 'дюгонь', 'sea lion': 'морской лев',
    # Собаки (много пород)
    'chihuahua': 'чихуахуа', 'japanese spaniel': 'японский спаниель',
    'maltese dog': 'мальтийская болонка', 'pekinese': 'пекинес',
    'shih-tzu': 'ши-тцу', 'blenheim spaniel': 'бленхеймский спаниель',
    'papillon': 'папийон', 'toy terrier': 'той-терьер', 'rhodesian ridgeback': 'родезийский риджбек',
    'afghan hound': 'афганская борзая', 'basset': 'бассет-хаунд', 'beagle': 'бигль',
    'bloodhound': 'бладхаунд', 'bluetick': 'блютик', 'black-and-tan coonhound': 'кунхаунд',
    'walker hound': 'уокер-хаунд', 'english foxhound': 'английский фоксхаунд',
    'redbone': 'редбон', 'borzoi': 'русская борзая', 'irish wolfhound': 'ирландский волкодав',
    'italian greyhound': 'итальянская борзая', 'whippet': 'уиппет',
    'ibizan hound': 'ивисская борзая', 'norwegian elkhound': 'норвежский элкхаунд',
    'otterhound': 'оттерхаунд', 'saluki': 'салюки', 'scottish deerhound': 'шотландский дирхаунд',
    'weimaraner': 'веймаранер', 'staffordshire bullterrier': 'стаффордширский бультерьер',
    'american staffordshire terrier': 'американский стаффордширский терьер',
    'bedlington terrier': 'бедлингтон-терьер', 'border terrier': 'бордер-терьер',
    'kerry blue terrier': 'керри-блю-терьер', 'irish terrier': 'ирландский терьер',
    'norfolk terrier': 'норфолк-терьер', 'norwich terrier': 'норвич-терьер',
    'yorkshire terrier': 'йоркширский терьер', 'wire-haired fox terrier': 'жесткошёрстный фокстерьер',
    'lakeland terrier': 'лейкленд-терьер', 'sealyham terrier': 'силихем-терьер',
    'airedale': 'эрдельтерьер', 'cairn': 'керн-терьер', 'australian terrier': 'австралийский терьер',
    'dandie dinmont': 'денди-динмонт-терьер', 'boston bull': 'бостон-терьер',
    'miniature schnauzer': 'миниатюрный шнауцер', 'giant schnauzer': 'гигантский шнауцер',
    'standard schnauzer': 'стандартный шнауцер', 'scotch terrier': 'шотландский терьер',
    'tibetan terrier': 'тибетский терьер', 'silky terrier': 'австралийский шёлковый терьер',
    'soft-coated wheaten terrier': 'мягкошёрстный пшеничный терьер',
    'west highland white terrier': 'вест-хайленд-уайт-терьер', 'lhasa': 'лхаса апсо',
    'flat-coated retriever': 'плоскошёрстный ретривер',
    'curly-coated retriever': 'кудрявошёрстный ретривер',
    'golden retriever': 'золотистый ретривер', 'labrador retriever': 'лабрадор-ретривер',
    'chesapeake bay retriever': 'чесапикский ретривер', 'german short-haired pointer': 'немецкий курцхаар',
    'vizsla': 'венгерская легавая', 'english setter': 'английский сеттер',
    'irish setter': 'ирландский сеттер', 'gordon setter': 'гордон-сеттер',
    'brittany spaniel': 'бретонский спаниель', 'clumber': 'кламбер-спаниель',
    'english springer': 'английский спрингер-спаниель',
    'welsh springer spaniel': 'вельш-спрингер-спаниель',
    'cocker spaniel': 'кокер-спаниель', 'sussex spaniel': 'суссекс-спаниель',
    'irish water spaniel': 'ирландский водяной спаниель', 'kuvasz': 'кувас',
    'schipperke': 'шипперке', 'groenendael': 'гронендаль', 'malinois': 'малинуа',
    'briard': 'бриар', 'kelpie': 'кelpie', 'komondor': 'комондор',
    'old english sheepdog': 'старая английская овчарка', 'shetland sheepdog': 'шелти',
    'collie': 'колли', 'border collie': 'бордер-колли', 'bouvier des flandres': 'бувье',
    'rottweiler': 'ротвейлер', 'german shepherd': 'немецкая овчарка',
    'doberman': 'доберман', 'miniature pinscher': 'карликовый пинчер',
    'greater swiss mountain dog': 'большой швейцарский зенненхунд',
    'bernese mountain dog': 'бернский зенненхунд', 'appenzeller': 'аппенцеллер',
    'entlebucher': 'энтлебухер', 'boxer': 'боксёр', 'bull mastiff': 'бульмастиф',
    'tibetan mastiff': 'тибетский мастиф', 'french bulldog': 'французский бульдог',
    'great dane': 'немецкий дог', 'saint bernard': 'сенбернар', 'eskimo dog': 'эскимосская лайка',
    'malamute': 'малямут', 'siberian husky': 'сибирский хаски',
    'dalmatian': 'далматин', 'affenpinscher': 'аффенпинчер',
    'basenji': 'басенджи', 'pug': 'мопс', 'leonberg': 'леонбергер',
    'newfoundland': 'ньюфаундленд', 'great pyrenees': 'пиренейская горная собака',
    'samoyed': 'самоед', 'pomeranian': 'шпиц', 'chow': 'чау-чау',
    'keeshond': 'кеесхонд', 'brabancon griffon': 'брабансон', 'pembroke': 'пемброк-вельш-корги',
    'cardigan': 'кардиган-вельш-корги', 'toy poodle': 'карликовый пудель',
    'miniature poodle': 'малый пудель', 'standard poodle': 'пудель',
    'mexican hairless': 'мексиканская лысая собака', 'timber wolf': 'серый волк',
    'white wolf': 'белый волк', 'red wolf': 'красный волк', 'coyote': 'койот',
    'dingo': 'динго', 'dhole': 'красный волк', 'african hunting dog': 'африканская охотничья собака',
    'hyena': 'гиена', 'red fox': 'красная лиса', 'kit fox': 'быстрая лиса',
    'arctic fox': 'арктическая лиса', 'grey fox': 'серая лиса',
    'tabby': 'полосатый кот', 'tiger cat': 'тигровый кот',
    'persian cat': 'персидская кошка', 'siamese cat': 'сиамская кошка',
    'egyptian cat': 'египетская кошка', 'cougar': 'пума', 'lynx': 'рысь',
    'leopard': 'леопард', 'snow leopard': 'снежный барс', 'jaguar': 'ягуар',
    'lion': 'лев', 'tiger': 'тигр', 'cheetah': 'гепард',
    'brown bear': 'бурый медведь', 'american black bear': 'американский чёрный медведь',
    'ice bear': 'белый медведь', 'sloth bear': 'медведь-губач',
    'mongoose': 'мангуст', 'meerkat': 'сурикат', 'tiger beetle': 'жук-скакун',
    'ladybug': 'божья коровка', 'ground beetle': 'жужелица', 'long-horned beetle': 'усач',
    'leaf beetle': 'листоед', 'dung beetle': 'навозник', 'rhinoceros beetle': 'жук-носорог',
    'weevil': 'долгоносик', 'fly': 'муха', 'bee': 'пчела', 'ant': 'муравей',
    'grasshopper': 'кузнечик', 'cricket': 'сверчок', 'walking stick': 'палочник',
    'cockroach': 'таракан', 'mantis': 'богомол', 'cicada': 'цикада',
    'leafhopper': 'цикадка', 'lacewing': 'сетчатокрылое', 'dragonfly': 'стрекоза',
    'damselfly': 'стрекоза-красотка', 'admiral': 'адмирал (бабочка)',
    'ringlet': 'бархатница', 'monarch': 'монарх (бабочка)', 'cabbage butterfly': 'капустница',
    'sulphur butterfly': 'желтушка', 'lycaenid': 'голубянка',
    'starfish': 'морская звезда', 'sea urchin': 'морской ёж', 'sea cucumber': 'голотурия',
    'wood rabbit': 'заяц', 'hare': 'заяц', 'angora': 'ангорский кролик',
    'hamster': 'хомяк', 'porcupine': 'дикобраз', 'fox squirrel': 'лисья белка',
    'marmot': 'сурок', 'beaver': 'бобёр', 'guinea pig': 'морская свинка',
    'sorrel': 'игреневая лошадь', 'zebra': 'зебра', 'hog': 'боров', 'wild boar': 'кабан',
    'warthog': 'бородавочник', 'hippopotamus': 'бегемот', 'ox': 'вол',
    'water buffalo': 'буйвол', 'bison': 'бизон', 'ram': 'баран',
    'bighorn': 'снежный баран', 'ibex': 'горный козёл', 'hartebeest': 'конгони',
    'impala': 'импала', 'gazelle': 'газель', 'arabian camel': 'одногорбый верблюд',
    'llama': 'лама', 'weasel': 'ласка', 'mink': 'норка', 'polecat': 'хорёк',
    'black-footed ferret': 'чёрноногий хорёк', 'otter': 'выдра', 'skunk': 'скунс',
    'badger': 'барсук', 'armadillo': 'броненосец', 'three-toed sloth': 'ленивец',
    'orangutan': 'орангутан', 'gorilla': 'горилла', 'chimpanzee': 'шимпанзе',
    'gibbon': 'гиббон', 'siamang': 'сиаманг', 'guenon': 'мартышка',
    'patas': 'патас', 'baboon': 'бабуин', 'macaque': 'макака',
    'langur': 'лангур', 'colobus': 'колобус', 'proboscis monkey': 'носатая обезьяна',
    'marmoset': 'мармозетка', 'capuchin': 'капуцин', 'howler monkey': 'ревун',
    'titi': 'тити', 'spider monkey': 'паукообразная обезьяна', 'squirrel monkey': 'саймири',
    'madagascar cat': 'мадагаскарская кошка', 'indri': 'индри',
    'indian elephant': 'индийский слон', 'african elephant': 'африканский слон',
    'lesser panda': 'малая панда', 'giant panda': 'большая панда',
    'barracouta': 'барракуда', 'eel': 'угорь', 'coho': 'кижуч',
    # Предметы и техника
    'laptop': 'ноутбук', 'notebook': 'ноутбук', 'desktop computer': 'настольный компьютер',
    'hand-held computer': 'карманный компьютер', 'space bar': 'клавиша пробела',
    'computer keyboard': 'клавиатура', 'typewriter keyboard': 'клавиатура печатной машинки',
    'printer': 'принтер', 'monitor': 'монитор', 'mouse': 'компьютерная мышь',
    'trackball': 'трекбол', 'modem': 'модем', 'router': 'роутер',
    'hard disc': 'жёсткий диск', 'disk brake': 'дисковый тормоз',
    'abacus': 'счёты', 'cash machine': 'банкомат', 'slide rule': 'логарифмическая линейка',
    'desktop': 'рабочий стол компьютера', 'pay-phone': 'таксофон',
    'cellular telephone': 'мобильный телефон', 'iPod': 'iPod',
    'digital clock': 'цифровые часы', 'wall clock': 'настенные часы',
    'hourglass': 'песочные часы', 'sundial': 'солнечные часы',
    'digital watch': 'цифровые наручные часы', 'analog clock': 'аналоговые часы',
    'stopwatch': 'секундомер', 'alarm clock': 'будильник',
    # Транспорт расширенный
    'beach wagon': 'универсал', 'cab': 'такси', 'convertible': 'кабриолет',
    'go-kart': 'карт', 'golfcart': 'гольф-карт', 'half track': 'полугусеничный',
    'jeep': 'джип', 'limousine': 'лимузин', 'minivan': 'минивэн',
    'model t': 'Форд Модель-Т', 'moving van': 'грузовой фургон',
    'police van': 'полицейский фургон', 'racer': 'гоночный автомобиль',
    'recreational vehicle': 'автодом', 'school bus': 'школьный автобус',
    'sports car': 'спортивный автомобиль', 'ambulance': 'машина скорой помощи',
    'streetcar': 'трамвай', 'tank': 'танк', 'tow truck': 'эвакуатор',
    'trolleybus': 'троллейбус', 'truck': 'грузовик', 'car': 'автомобиль',
    'bicycle': 'велосипед', 'mountain bike': 'горный велосипед', 'moped': 'мопед',
    'scooter': 'скутер', 'motorcycle': 'мотоцикл', 'motor scooter': 'мотоскутер',
    'snowmobile': 'снегоход', 'snowplow': 'снегоуборщик',
    'freight car': 'товарный вагон', 'locomotive': 'локомотив',
    'bullet train': 'поезд-пуля', 'passenger car': 'пассажирский вагон',
    'airliner': 'авиалайнер', 'airship': 'дирижабль', 'balloon': 'воздушный шар',
    'warplane': 'военный самолёт', 'wing': 'крыло самолёта',
    'space shuttle': 'космический шаттл', 'capsule': 'космическая капсула',
    'parachute': 'парашют', 'projectile': 'снаряд', 'missile': 'ракета',
    'aircraft carrier': 'авианосец', 'container ship': 'контейнеровоз',
    'lifeboat': 'спасательная шлюпка', 'speedboat': 'скоростной катер',
    'sailboat': 'парусник', 'canoe': 'каноэ', 'catamaran': 'катамаран',
    'gondola': 'гондола', 'fireboat': 'пожарный катер', 'submarine': 'подводная лодка',
    'schooner': 'шхуна', 'yawl': 'яул', 'rowboat': 'гребная лодка',
    # Еда
    'pizza': 'пицца', 'hamburger': 'гамбургер', 'hotdog': 'хот-дог',
    'meatloaf': 'мясной рулет', 'potpie': 'пирог с мясом', 'burrito': 'буррито',
    'sandwich': 'сэндвич', 'ice cream': 'мороженое', 'waffle': 'вафля',
    'pretzel': 'крендель', 'bagel': 'бублик', 'banana': 'банан',
    'apple': 'яблоко', 'orange': 'апельсин', 'lemon': 'лимон',
    'fig': 'инжир', 'pineapple': 'ананас', 'strawberry': 'клубника',
    'cucumber': 'огурец', 'artichoke': 'артишок', 'bell pepper': 'болгарский перец',
    'mushroom': 'гриб', 'corn': 'кукуруза', 'acorn squash': 'желудёвая тыква',
    'butternut squash': 'мускатная тыква', 'zucchini': 'кабачок',
    'spaghetti squash': 'спагетти-тыква', 'broccoli': 'брокколи',
    'cauliflower': 'цветная капуста', 'head cabbage': 'кочанная капуста',
    'carbonara': 'карбонара', 'chocolate sauce': 'шоколадный соус',
    'dough': 'тесто', 'meat loaf': 'мясной хлеб', 'guacamole': 'гуакамоле',
    'consomme': 'консоме', 'hot pot': 'хот-пот', 'trifle': 'трайфл',
    'eggnog': 'эггног', 'cup': 'кружка', 'coffee mug': 'кофейная кружка',
    'espresso': 'эспрессо', 'beer glass': 'бокал пива', 'wine bottle': 'бутылка вина',
    'red wine': 'красное вино', 'pop bottle': 'бутылка газировки',
    'water bottle': 'бутылка воды', 'milk can': 'молочный бидон',
    # Одежда
    'stole': 'шарф', 'maillot': 'купальник', 'bikini': 'бикини',
    'brassiere': 'бюстгальтер', 'apron': 'фартук', 'lab coat': 'лабораторный халат',
    'cardigan': 'кардиган', 'suit': 'деловой костюм', 'jersey': 'джерси',
    'jean': 'джинсы', 'miniskirt': 'мини-юбка', 'bow tie': 'бабочка',
    'bolo tie': 'болотай', 'neck brace': 'ортопедический воротник',
    'mortarboard': 'академическая шапочка', 'academic gown': 'академическая мантия',
    'groom': 'жених', 'military uniform': 'военная форма',
    'abaya': 'абая', 'overskirt': 'юбка-накидка', 'sarong': 'саронг',
    'cowboy boot': 'ковбойские сапоги', 'cowboy hat': 'ковбойская шляпа',
    'sunglasses': 'солнечные очки', 'ski mask': 'лыжная маска', 'gas mask': 'противогаз',
    'backpack': 'рюкзак', 'purse': 'сумочка', 'wallet': 'кошелёк',
    'shopping basket': 'корзина для покупок', 'shopping cart': 'тележка для покупок',
    'umbrella': 'зонт', 'safety pin': 'английская булавка', 'thimble': 'напёрсток',
    # Инструменты
    'hammer': 'молоток', 'nail': 'гвоздь', 'screwdriver': 'отвёртка',
    'power drill': 'дрель', 'jack-o-lantern': 'светильник Джека', 'hand blower': 'фен',
    'chainsaw': 'бензопила', 'lawn mower': 'газонокосилка',
    'harvester': 'комбайн', 'thresher': 'молотилка', 'tractor': 'трактор',
    'crane': 'кран', 'excavator': 'экскаватор', 'forklift': 'вилочный погрузчик',
    'bulldozer': 'бульдозер', 'plow': 'плуг',
    # Мебель и интерьер
    'four-poster': 'кровать с балдахином', 'wardrobe': 'шкаф', 'chiffonier': 'шифоньер',
    'bookcase': 'книжный шкаф', 'china cabinet': 'буфет', 'table lamp': 'настольная лампа',
    'studio couch': 'диван-кровать', 'throne': 'трон', 'toilet seat': 'сиденье унитаза',
    'bathtub': 'ванна', 'shower curtain': 'занавеска для душа', 'medicine chest': 'аптечка',
    'window shade': 'оконная штора', 'window screen': 'оконная сетка',
    'mosquito net': 'москитная сетка',
    # Спорт
    'basketball': 'баскетбольный мяч', 'soccer ball': 'футбольный мяч',
    'volleyball': 'волейбольный мяч', 'rugby ball': 'мяч для регби',
    'golf ball': 'мяч для гольфа', 'tennis ball': 'теннисный мяч',
    'cricket ball': 'мяч для крикета', 'baseball': 'бейсбольный мяч',
    'croquet ball': 'мяч для крокета', 'punching bag': 'боксёрский мешок',
    'volleyball': 'волейбольный мяч', 'ping-pong ball': 'шарик для пинг-понга',
    'frisbee': 'фрисби', 'skateboard': 'скейтборд', 'snowboard': 'сноуборд',
    'skis': 'лыжи', 'ski': 'лыжа', 'sled': 'сани', 'snowshoe': 'снегоступы',
    'canoe': 'каноэ', 'surfboard': 'доска для сёрфинга',
    'unicycle': 'одноколёсный велосипед', 'balance beam': 'бревно',
    'parallel bars': 'брусья', 'barbell': 'штанга', 'dumbbell': 'гантель',
    # Природа и здания
    'coral reef': 'коралловый риф', 'boathouse': 'лодочный сарай',
    'cliff dwelling': 'скальное жилище', 'monastery': 'монастырь',
    'church': 'церковь', 'mosque': 'мечеть', 'stupa': 'ступа',
    'pagoda': 'пагода', 'barn': 'амбар', 'greenhouse': 'теплица',
    'palace': 'дворец', 'castle': 'замок', 'library': 'библиотека',
    'prison': 'тюрьма', 'restaurant': 'ресторан', 'cinema': 'кинотеатр',
    'swimming pool': 'бассейн', 'fountain': 'фонтан', 'bridge': 'мост',
    'viaduct': 'виадук', 'suspension bridge': 'подвесной мост',
    'steel arch bridge': 'стальной арочный мост', 'dam': 'плотина',
    'lighthouse': 'маяк', 'pier': 'пирс', 'dock': 'доки',
    'volcano': 'вулкан', 'valley': 'долина', 'alp': 'горный луг',
    'geyser': 'гейзер', 'lakeside': 'берег озера', 'seashore': 'морской берег',
    'promontory': 'мыс', 'shoal': 'мелководье', 'reef': 'риф',
    'corn field': 'кукурузное поле', 'rice paddy': 'рисовые поля',
    'thatch': 'соломенная крыша', 'greenhouse': 'теплица',
    'stone wall': 'каменная стена', 'picket fence': 'штакетный забор',
    'chainlink fence': 'сетчатый забор', 'bannister': 'перила',
    'breakwater': 'волнорез', 'sandbar': 'песчаная коса',
    'maze': 'лабиринт', 'park bench': 'парковая скамейка',
}

def imagenet_to_ru(class_name: str) -> str:
    """Переводит ImageNet class name на русский."""
    key = class_name.lower().strip()
    if key in IMAGENET_RU:
        return IMAGENET_RU[key]
    # частичное совпадение
    for k, v in IMAGENET_RU.items():
        if k in key:
            return v
    # fallback
    return class_name.replace('_', ' ').capitalize()


# ── ImageNet Predictor ────────────────────────────────────────
class ImageNetPredictor:
    """ResNet-50 предобученный на ImageNet. 1000 классов, точность ~76%."""

    def __init__(self, device: str = 'cpu'):
        self.device = torch.device(device)
        print("[ImageNet] Загружаю ResNet-50 (предобученный ImageNet V2)...")
        self.model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V2)
        self.model.eval()
        self.model.to(self.device)
        self.classes_en = models.ResNet50_Weights.IMAGENET1K_V2.meta['categories']
        self.transform  = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
        print(f"[ImageNet] Готово. Классов: {len(self.classes_en)}")

    def predict(self, image: Image.Image) -> Dict:
        tensor = self.transform(image.convert('RGB')).unsqueeze(0).to(self.device)
        with torch.no_grad():
            probs = F.softmax(self.model(tensor), dim=1).squeeze(0).cpu().numpy()
        top5_idx = probs.argsort()[::-1][:5]
        return {
            'prediction':    imagenet_to_ru(self.classes_en[top5_idx[0]]),
            'prediction_en': self.classes_en[top5_idx[0]],
            'confidence':    round(float(probs[top5_idx[0]]) * 100, 2),
            'model':         'ResNet-50 ImageNet',
            'top5': [
                {'class': imagenet_to_ru(self.classes_en[i]), 'class_en': self.classes_en[i],
                 'confidence': round(float(probs[i]) * 100, 2)}
                for i in top5_idx
            ],
            'all_probs': {
                imagenet_to_ru(self.classes_en[i]): round(float(p) * 100, 4)
                for i, p in enumerate(probs)
            },
        }

    def info(self) -> Dict:
        p = sum(x.numel() for x in self.model.parameters())
        return {
            'architecture':     'ResNet-50 (Pretrained ImageNet V2)',
            'total_params':     p,
            'total_params_fmt': f'{p / 1e6:.1f}M',
            'dataset':          'ImageNet (1000 классов)',
            'num_classes':      len(self.classes_en),
            'classes':          [imagenet_to_ru(c) for c in self.classes_en[:30]] + ['...'],
            'best_val_acc':     76.0,
            'current_epoch':    0,
            'is_training':      False,
            'mode':             'pretrained',
        }


# ── VisionNet для CIFAR-10 ────────────────────────────────────
class SEBlock(nn.Module):
    def __init__(self, ch, r=16):
        super().__init__()
        m = max(ch // r, 4)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.fc   = nn.Sequential(nn.Linear(ch, m, False), nn.ReLU(True), nn.Linear(m, ch, False), nn.Sigmoid())
    def forward(self, x):
        b, c, _, _ = x.size(); w = self.pool(x).view(b, c); return x * self.fc(w).view(b, c, 1, 1)

class ResBlock(nn.Module):
    def __init__(self, ic, oc, s=1, d=0.05):
        super().__init__()
        self.main = nn.Sequential(nn.Conv2d(ic,oc,3,s,1,bias=False),nn.BatchNorm2d(oc),nn.ReLU(True),nn.Dropout2d(d),nn.Conv2d(oc,oc,3,1,1,bias=False),nn.BatchNorm2d(oc))
        self.se   = SEBlock(oc)
        self.relu = nn.ReLU(True)
        self.skip = nn.Sequential(nn.Conv2d(ic,oc,1,s,bias=False),nn.BatchNorm2d(oc)) if s!=1 or ic!=oc else nn.Sequential()
    def forward(self, x): return self.relu(self.se(self.main(x)) + self.skip(x))

class VisionNet(nn.Module):
    CIFAR10_CLASSES = ['самолёт','автомобиль','птица','кот','олень','собака','лягушка','лошадь','корабль','грузовик']
    MNIST_CLASSES   = [str(i) for i in range(10)]
    def __init__(self, nc=10, ic=3):
        super().__init__()
        self.stem  = nn.Sequential(nn.Conv2d(ic,64,3,1,1,bias=False),nn.BatchNorm2d(64),nn.ReLU(True))
        self.s1    = nn.Sequential(ResBlock(64,64,1),SEBlock(64))
        self.s2    = nn.Sequential(ResBlock(64,128,2),SEBlock(128))
        self.s3    = nn.Sequential(ResBlock(128,256,2),SEBlock(256))
        self.s4    = nn.Sequential(ResBlock(256,512,2),SEBlock(512))
        self.pool  = nn.AdaptiveAvgPool2d(1)
        self.head  = nn.Sequential(nn.Flatten(),nn.Linear(512,256),nn.ReLU(True),nn.Dropout(0.3),nn.Linear(256,nc))
        for m in self.modules():
            if isinstance(m, nn.Conv2d): nn.init.kaiming_normal_(m.weight,mode='fan_out',nonlinearity='relu')
            elif isinstance(m, nn.BatchNorm2d): nn.init.constant_(m.weight,1); nn.init.constant_(m.bias,0)
            elif isinstance(m, nn.Linear):
                nn.init.xavier_normal_(m.weight)
                if m.bias is not None: nn.init.zeros_(m.bias)
    def forward(self, x): return self.head(self.pool(self.s4(self.s3(self.s2(self.s1(self.stem(x)))))))
    def predict_proba(self, x): return F.softmax(self.forward(x), dim=-1)
    @property
    def num_params(self): return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ── VisionTrainer ─────────────────────────────────────────────
class VisionTrainer:
    """
    dataset='imagenet' → ResNet-50 предобученный, 1000 классов, работает сразу
    dataset='cifar10'  → VisionNet кастомная, 10 классов, требует обучения
    """

    def __init__(self, dataset='imagenet', device='cpu', save_dir='./checkpoints'):
        self.dataset  = dataset
        self.device   = torch.device(device)
        self.save_dir = save_dir
        os.makedirs(save_dir, exist_ok=True)
        self.training = False
        self.epoch    = 0
        self.callback: Optional[Callable] = None
        self.history  = {'train_loss':[], 'val_loss':[], 'train_acc':[], 'val_acc':[]}
        self.best_acc = 0.0

        if dataset == 'imagenet':
            self._inet  = ImageNetPredictor(device)
            self.classes = [imagenet_to_ru(c) for c in self._inet.classes_en]
            self.model   = self._inet.model
        else:
            self._inet = None
            self.classes = VisionNet.CIFAR10_CLASSES if dataset == 'cifar10' else VisionNet.MNIST_CLASSES
            self.in_ch   = 3 if dataset == 'cifar10' else 1
            self.model   = VisionNet(len(self.classes), self.in_ch).to(self.device)
            self._try_load()

    def predict(self, image: Image.Image) -> Dict:
        if self._inet:
            return self._inet.predict(image)
        tf = transforms.Compose([
            transforms.Resize((32, 32)), transforms.ToTensor(),
            transforms.Normalize((0.4914,0.4822,0.4465),(0.2023,0.1994,0.2010)),
        ])
        t = tf(image.convert('RGB')).unsqueeze(0).to(self.device)
        self.model.eval()
        with torch.no_grad():
            probs = self.model.predict_proba(t).squeeze(0).cpu().numpy()
        top5 = probs.argsort()[::-1][:5]
        return {
            'prediction': self.classes[top5[0]],
            'confidence': round(float(probs[top5[0]])*100, 2),
            'model': 'VisionNet CIFAR-10',
            'top5': [{'class':self.classes[i],'confidence':round(float(probs[i])*100,2)} for i in top5],
            'all_probs': {self.classes[i]:round(float(p)*100,2) for i,p in enumerate(probs)},
        }

    def info(self) -> Dict:
        if self._inet: return self._inet.info()
        p = self.model.num_params
        return {'architecture':'VisionNet (ResBlock+SE)','total_params':p,'total_params_fmt':f'{p/1e6:.2f}M',
                'dataset':self.dataset.upper(),'num_classes':len(self.classes),'classes':self.classes,
                'best_val_acc':round(self.best_acc*100,2),'current_epoch':self.epoch,'is_training':self.training,'mode':'trainable'}

    def train(self, epochs=15, lr=0.001, batch_size=64, weight_decay=1e-4):
        if self._inet:
            raise ValueError("ImageNet режим не требует обучения")
        DS = datasets.CIFAR10 if self.dataset=='cifar10' else datasets.MNIST
        mn,st=(0.4914,0.4822,0.4465),(0.2023,0.1994,0.2010)
        tf_tr=transforms.Compose([transforms.RandomCrop(32,padding=4),transforms.RandomHorizontalFlip(),transforms.ColorJitter(0.2,0.2,0.2),transforms.ToTensor(),transforms.Normalize(mn,st)])
        tf_va=transforms.Compose([transforms.ToTensor(),transforms.Normalize(mn,st)])
        ft=DS('./data',train=True,download=True,transform=tf_tr)
        nv=int(len(ft)*0.1); tr,va=torch.utils.data.random_split(ft,[len(ft)-nv,nv],generator=torch.Generator().manual_seed(42))
        tdl=DataLoader(tr,batch_size,shuffle=True,num_workers=0); vdl=DataLoader(va,batch_size,shuffle=False,num_workers=0)
        opt=optim.AdamW(self.model.parameters(),lr=lr,weight_decay=weight_decay)
        sch=optim.lr_scheduler.CosineAnnealingLR(opt,T_max=epochs)
        crit=nn.CrossEntropyLoss(label_smoothing=0.1)
        self.training=True
        for ep in range(1,epochs+1):
            if not self.training: break
            self.epoch=ep; self.model.train(); tl=tc=tt=0
            for imgs,lbls in tdl:
                imgs,lbls=imgs.to(self.device),lbls.to(self.device); opt.zero_grad()
                out=self.model(imgs); loss=crit(out,lbls); loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(),1.0); opt.step()
                tl+=loss.item()*imgs.size(0); tc+=(out.argmax(1)==lbls).sum().item(); tt+=imgs.size(0)
            tl/=tt; ta=tc/tt; sch.step(); vl,va2=self._eval(vdl,crit)
            self.history['train_loss'].append(round(tl,4)); self.history['val_loss'].append(round(vl,4))
            self.history['train_acc'].append(round(ta,4)); self.history['val_acc'].append(round(va2,4))
            if va2>self.best_acc: self.best_acc=va2; self._save('best.pth')
            if self.callback: self.callback({'epoch':ep,'total':epochs,'train_loss':round(tl,4),'val_loss':round(vl,4),'train_acc':round(ta*100,2),'val_acc':round(va2*100,2),'best_acc':round(self.best_acc*100,2),'lr':round(sch.get_last_lr()[0],6)})
        self.training=False; self._save('last.pth'); return self.history

    def _eval(self, dl, crit):
        self.model.eval(); tl=tc=tt=0
        with torch.no_grad():
            for imgs,lbls in dl:
                imgs,lbls=imgs.to(self.device),lbls.to(self.device); out=self.model(imgs)
                tl+=crit(out,lbls).item()*imgs.size(0); tc+=(out.argmax(1)==lbls).sum().item(); tt+=imgs.size(0)
        return tl/tt,tc/tt

    def stop(self): self.training=False

    def _save(self, name):
        torch.save({'epoch':self.epoch,'model_state':self.model.state_dict(),'best_acc':self.best_acc,'history':self.history,'dataset':self.dataset,'classes':self.classes},os.path.join(self.save_dir,name))

    def _try_load(self, name='best.pth'):
        path=os.path.join(self.save_dir,name)
        if not os.path.exists(path): return
        try:
            ck=torch.load(path,map_location=self.device); self.model.load_state_dict(ck['model_state'])
            self.best_acc=ck.get('best_acc',0.0); self.epoch=ck.get('epoch',0); self.history=ck.get('history',self.history)
        except Exception: pass