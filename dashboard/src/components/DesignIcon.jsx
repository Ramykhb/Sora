// Original editable icon exports from the Sora Figma design.
const assets = { logo: 'imgFrame', overview: 'imgFrame1', video: 'imgFrame2', image: 'imgFrame3', message: 'imgFrame4', settings: 'imgFrame5', accessibility: 'imgFrame6', search: 'imgFrame7', bell: 'imgFrame8', sound: 'imgFrame10', expand: 'imgFrame11', mic: 'imgFrame13', answer: 'imgFrame14' };
export default function DesignIcon({ name, active = false }) {
  return <img className={`design-icon${active ? ' active-icon' : ''}`} src={`${import.meta.env.BASE_URL}design/${assets[name]}.svg`} alt="" aria-hidden="true" />;
}
