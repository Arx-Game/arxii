import { Controller, useForm } from 'react-hook-form';
import Select from 'react-select';
import { useTenureGalleriesQuery, useUploadPlayerMedia, useAssociateMedia } from '../queries';
import MyTenureSelect from '@/components/MyTenureSelect';

interface Option {
  value: number;
  label: string;
}

interface UploadFormValues {
  image_file: FileList;
  title: string;
  description: string;
  tenure: number | null;
  gallery: Option | null;
}

export function MediaUploadForm({ onUploadComplete }: { onUploadComplete?: () => void }) {
  const uploadMutation = useUploadPlayerMedia();
  const associateMutation = useAssociateMedia();

  const { register, control, handleSubmit, reset, watch } = useForm<UploadFormValues>({
    defaultValues: { tenure: null, gallery: null },
  });

  const tenureId = watch('tenure');
  const { data: galleries } = useTenureGalleriesQuery(tenureId);

  const onSubmit = async (data: UploadFormValues) => {
    const formData = new FormData();
    formData.append('image_file', data.image_file[0]);
    if (data.title) formData.append('title', data.title);
    if (data.description) formData.append('description', data.description);
    const result = await uploadMutation.mutateAsync(formData);
    if (data.tenure) {
      await associateMutation.mutateAsync({
        mediaId: result.id,
        tenureId: data.tenure,
        galleryId: data.gallery?.value,
      });
    }
    reset();
    onUploadComplete?.();
  };

  const galleryOptions = galleries?.map((g) => ({ value: g.id, label: g.name })) ?? [];

  return (
    <section className="space-y-2">
      <h3 className="text-lg font-semibold">Upload Media</h3>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-2">
        <input type="file" {...register('image_file', { required: true })} />
        <input type="text" placeholder="Title" {...register('title')} className="block" />
        <textarea placeholder="Description" {...register('description')} className="block" />
        <Controller
          name="tenure"
          control={control}
          render={({ field }) => <MyTenureSelect value={field.value} onChange={field.onChange} />}
        />
        {tenureId && (
          <Controller
            name="gallery"
            control={control}
            render={({ field }) => (
              <Select
                {...field}
                options={galleryOptions}
                isClearable
                placeholder="Select Gallery"
              />
            )}
          />
        )}
        <button type="submit" className="rounded bg-blue-500 px-2 py-1 text-white">
          Upload
        </button>
      </form>
    </section>
  );
}
