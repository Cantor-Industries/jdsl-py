// Animated glitch ASCII logo for the jdsl docs landing page.
// No-op when #ascii-art is absent, and honors prefers-reduced-motion.
(function () {
  "use strict";

  var artElement = document.getElementById("ascii-art");
  if (!artElement) return;

  var targetArt = `        _        _            _            _      
       /\\ \\     /\\ \\         / /\\         _\\ \\    
       \\ \\ \\   /  \\ \\____   / /  \\       /\\__ \\   
        /\\ \\_\\ / /\\ \\_____\\ / / /\\ \\__   / /_ \\_\\ 
       / /\\_// / /\\/___  // / /\\ \\___\\ / / /\\/_/ 
  _   / / /  / / /   / / / \\ \\ \\ \\/___// / /      
 /\\ \\ / / /  / / /   / / /   \\ \\ \\     / / /       
 \\ \\_\\/ / /  / / /   / / /_    \\ \\ \\   / / / ____  
  / / /_/ / /  \\ \\__/ / //_\\__/ / /  / /_/_/ ___/\\ 
 / / /__\\/ /    \\ \\___\\/ / \\ \\/___/ /  /_______/\\__/ 
\\/_______/      \\/_____/   \\_____\\/   \\_______\\/`;

  var glitchChars = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. ";
  var originalGrid = targetArt.split("\n").map(function (line) {
    return line.split("");
  });

  var fps = 10;                  // refresh rate
  var glitchProbability = 0.37;  // per-character flicker rate
  var timerId = null;

  function renderFrame() {
    var out = "";
    for (var r = 0; r < originalGrid.length; r++) {
      for (var c = 0; c < originalGrid[r].length; c++) {
        var ch = originalGrid[r][c];
        if (ch === " ") {
          out += " ";
          continue;
        }
        out += Math.random() < glitchProbability
          ? glitchChars[Math.floor(Math.random() * glitchChars.length)]
          : ch;
      }
      out += "\n";
    }
    artElement.textContent = out;
  }

  function startAnimation() {
    if (timerId) clearInterval(timerId);
    timerId = setInterval(renderFrame, 1000 / fps);
  }

  var reduced =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (reduced) {
    renderFrame();
  } else {
    startAnimation();
  }
})();
