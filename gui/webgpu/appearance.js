export const lightBackground={r:.91,g:.94,b:.96,a:1};
export const darkBackground={r:20/255,g:28/255,b:36/255,a:1};

export function watchSystemBackground(update,media=matchMedia('(prefers-color-scheme: dark)')) {
 const apply=()=>update(media.matches?darkBackground:lightBackground);
 media.addEventListener('change',apply);apply();
 return ()=>media.removeEventListener('change',apply);
}
