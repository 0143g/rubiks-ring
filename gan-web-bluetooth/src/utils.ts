
const REID_EDGE_ORDER = "UF UR UB UL DF DR DB DL FR FL BR BL".split(" ");
const REID_CORNER_ORDER = "UFR URB UBL ULF DRF DFL DLB DBR".split(" ");
const REID_CENTER_ORDER = "U L F R B D".split(" ");

const REID_TO_FACELETS_MAP: [number, number, number][] = [
  [1, 2, 0],
  [0, 2, 0],
  [1, 1, 0],
  [0, 3, 0],
  [2, 0, 0],
  [0, 1, 0],
  [1, 3, 0],
  [0, 0, 0],
  [1, 0, 0],
  [1, 0, 2],
  [0, 1, 1],
  [1, 1, 1],
  [0, 8, 1],
  [2, 3, 0],
  [0, 10, 1],
  [1, 4, 1],
  [0, 5, 1],
  [1, 7, 2],
  [1, 3, 2],
  [0, 0, 1],
  [1, 0, 1],
  [0, 9, 0],
  [2, 2, 0],
  [0, 8, 0],
  [1, 5, 1],
  [0, 4, 1],
  [1, 4, 2],
  [1, 5, 0],
  [0, 4, 0],
  [1, 4, 0],
  [0, 7, 0],
  [2, 5, 0],
  [0, 5, 0],
  [1, 6, 0],
  [0, 6, 0],
  [1, 7, 0],
  [1, 2, 2],
  [0, 3, 1],
  [1, 3, 1],
  [0, 11, 1],
  [2, 1, 0],
  [0, 9, 1],
  [1, 6, 1],
  [0, 7, 1],
  [1, 5, 2],
  [1, 1, 2],
  [0, 2, 1],
  [1, 2, 1],
  [0, 10, 0],
  [2, 4, 0],
  [0, 11, 0],
  [1, 7, 1],
  [0, 6, 1],
  [1, 6, 2],
];

const CORNER_MAPPING = [
  [0, 21, 15],
  [5, 13, 47],
  [7, 45, 39],
  [2, 37, 23],
  [29, 10, 16],
  [31, 18, 32],
  [26, 34, 40],
  [24, 42, 8],
];

const EDGE_MAPPING = [
  [1, 22],
  [3, 14],
  [6, 46],
  [4, 38],
  [30, 17],
  [27, 9],
  [25, 41],
  [28, 33],
  [19, 12],
  [20, 35],
  [44, 11],
  [43, 36],
];

const FACE_ORDER = "URFDLB";

const PIECE_MAP = {};

REID_EDGE_ORDER.forEach((edge, idx) => {
  for (let i = 0; i < 2; i++) {
    PIECE_MAP[rotateLeft(edge, i)] = { piece: idx, orientation: i };
  }
});

REID_CORNER_ORDER.forEach((corner, idx) => {
  for (let i = 0; i < 3; i++) {
    PIECE_MAP[rotateLeft(corner, i)] = { piece: idx, orientation: i };
  }
});

function rotateLeft(s, i) {
  return s.slice(i) + s.slice(0, i);
}

function toReid333Struct(pattern) {
  const output = [[], []];
  for (let i = 0; i < 6; i++) {
    if (pattern.patternData["CENTERS"].pieces[i] !== i) {
      throw new Error("non-oriented puzzles are not supported");
    }
  }
  for (let i = 0; i < 12; i++) {
    output[0].push(
      rotateLeft(
        REID_EDGE_ORDER[pattern.patternData["EDGES"].pieces[i]],
        pattern.patternData["EDGES"].orientation[i],
      ),
    );
  }
  for (let i = 0; i < 8; i++) {
    output[1].push(
      rotateLeft(
        REID_CORNER_ORDER[pattern.patternData["CORNERS"].pieces[i]],
        pattern.patternData["CORNERS"].orientation[i],
      ),
    );
  }
  output.push(REID_CENTER_ORDER);
  return output;
}

function patternToFacelets(pattern) {
  const reid = toReid333Struct(pattern);
  return REID_TO_FACELETS_MAP.map(([orbit, perm, ori]) => reid[orbit][perm][ori]).join("");
}

function faceletsToPattern(facelets) {

  const stickers = [];
  facelets.match(/.{9}/g)?.forEach(face => {
    face.split('').reverse().forEach((s, i) => {
      if (i != 4)
        stickers.push(FACE_ORDER.indexOf(s));
    });
  });

  const patternData = {
    CORNERS: {
      pieces: [],
      orientation: [],
    },
    EDGES: {
      pieces: [],
      orientation: [],
    },
    CENTERS: {
      pieces: [0, 1, 2, 3, 4, 5],
      orientation: [0, 0, 0, 0, 0, 0],
      orientationMod: [1, 1, 1, 1, 1, 1]
    },
  };

  for (const cm of CORNER_MAPPING) {
    const pi = PIECE_MAP[cm.map((i) => FACE_ORDER[stickers[i]]).join('')];
    patternData.CORNERS.pieces.push(pi.piece);
    patternData.CORNERS.orientation.push(pi.orientation);
  }

  for (const em of EDGE_MAPPING) {
    const pi = PIECE_MAP[em.map((i) => FACE_ORDER[stickers[i]]).join('')];
    patternData.EDGES.pieces.push(pi.piece);
    patternData.EDGES.orientation.push(pi.orientation);
  }

  return patternData;

}

export {
  patternToFacelets,
  faceletsToPattern
}
